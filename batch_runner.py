import sqlite3
import time
import pandas as pd
import os
import json
from datetime import datetime
import pytz
import numpy as np

from outlier_find.find import find_outliers_and_mark
from outlier_fix.predict import correct_last_row_outlier
from app_details.alarms_db import (
    initialize_alarms_db,
    insert_alarm_rows,
    update_alarm_correction_with_value,
    save_corrected_sensor_data,
    load_settings,
    get_last_processed_measurement_id,
    save_last_processed_measurement_id,
    save_vpd_solution_alarm,
)
from outlier_fix.train_models_rt import main as train_models_rt_main
from solution.vpd_model import suggest_low_energy_vpd_control

SENSOR_DB_PATH = "sensor_data.db"
SETTINGS_FILE = "config/settings.json"
KST = pytz.timezone("Asia/Seoul")


def load_new_sensor_data(last_id=None, batch_size=1000):
    conn = sqlite3.connect(SENSOR_DB_PATH)
    if last_id is None:
        query = """
            SELECT * FROM measurements
            ORDER BY id ASC
            LIMIT ?
        """
        df = pd.read_sql(query, conn, params=(batch_size,))
    else:
        query = """
            SELECT * FROM measurements
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
        """
        df = pd.read_sql(query, conn, params=(last_id, batch_size))
    conn.close()
    return df


def calculate_vpd_scalar(T, RH):
    """단일 값 VPD 계산 (kPa)"""
    es = 0.6108 * np.exp((17.27 * T) / (T + 237.3))
    ea = es * (RH / 100.0)
    vpd = es - ea
    return float(vpd)


def should_run_training_today(settings, last_train_date_str):
    auto_time_str = settings.get("auto_train_time", "17:15")
    now = datetime.now(KST)
    today = now.date()

    if last_train_date_str:
        try:
            last_train_date = datetime.strptime(last_train_date_str, "%Y-%m-%d").date()
        except ValueError:
            last_train_date = None
    else:
        last_train_date = None

    if last_train_date == today:
        return False

    try:
        auto_hour, auto_minute = map(int, auto_time_str.split(":"))
    except Exception:
        auto_hour, auto_minute = 17, 15

    auto_run_dt = datetime(
        year=now.year, month=now.month, day=now.day,
        hour=auto_hour, minute=auto_minute, tzinfo=KST
    )

    return now >= auto_run_dt


def main_loop(interval_sec=60, vpd_threshold=1.5):
    initialize_alarms_db()

    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = load_settings()

    alert_enabled = settings.get("alert_enabled", True)
    print(f"시스템 시작 - 알림 활성화: {alert_enabled}")

    last_id = get_last_processed_measurement_id()
    last_train_date_str = None

    while True:
        # 1) 하루 한 번 자동 학습
        if should_run_training_today(settings, last_train_date_str):
            print("자동 모델 학습 시작...")
            train_models_rt_main()
            last_train_date_str = datetime.now(KST).strftime("%Y-%m-%d")

        # 2) 알림 비활성 모드
        if not alert_enabled:
            print("알림 비활성화 상태 - 5분 대기")
            time.sleep(300)
            continue

        # 3) 새 센서 데이터 로드
        df_new = load_new_sensor_data(last_id=last_id, batch_size=1000)

        if df_new.empty:
            time.sleep(interval_sec)
            continue

        max_id = int(df_new["id"].max())

        # 4) 이상치 탐지 + 마지막 행 자동 보정
        cleaned_df, alarm_df = find_outliers_and_mark(df_new, datetime_col="time_str")
        corrected_df, msg, target_sensor, predicted_value = correct_last_row_outlier(
            cleaned_df, settings=settings
        )

        # 5) 이상치 알림 저장
        if not alarm_df.empty:
            insert_alarm_rows(alarm_df)
            print(f"알림 {len(alarm_df)}건 저장")

        # 6) 보정내용/보정값 업데이트
        if target_sensor is not None and predicted_value is not None:
            sensor_map = {
                "Temperature": "온도",
                "Humidity": "습도",
                "Solar_Radiation": "광",
            }
            alarm_type = sensor_map.get(target_sensor)
            if alarm_type:
                last_time_str = str(corrected_df.iloc[-1, 0])
                now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                cs = f"자동 보정 ({now_kst})"
                cd = msg
                cv = predicted_value
                updated = update_alarm_correction_with_value(
                    last_time_str, alarm_type, cs, cv, cd
                )
                if updated:
                    print(f"보정 완료: {msg}")
                else:
                    print("보정 알림 업데이트 실패")

        # 7) 보정된 데이터 전체 저장
        save_corrected_sensor_data(corrected_df, settings=settings)

        # 8) 마지막 행 기준 VPD 솔루션 계산/저장
        try:
            last_row = corrected_df.iloc[-1]
            time_str = str(last_row.iloc[0])  # 첫 번째 컬럼이 time_str

            # settings 인덱스 기반 온도/습도 컬럼 위치
            h_loc = settings.get("h_location", 2)
            t_loc = settings.get("t_location", 3)
            cols = corrected_df.columns.tolist()
            T_now = float(last_row[cols[t_loc]])
            RH_now = float(last_row[cols[h_loc]])

            if not (np.isnan(T_now) or np.isnan(RH_now)):
                vpd_now = calculate_vpd_scalar(T_now, RH_now)
                print(f"[VPD] 마지막 행: T={T_now:.2f}°C, RH={RH_now:.1f}%, VPD={vpd_now:.2f} kPa")

                if vpd_now > vpd_threshold:
                    best = suggest_low_energy_vpd_control(
                        T_now=T_now,
                        RH_now=RH_now,
                        VPD_target=vpd_threshold,
                        floor_area_m2=1.0,
                        height_m=4.0,
                        T_cool_range_deg=5.0,
                        I_inside_Wm2=None,
                        verbose=False,
                    )

                    if best.get("status") in ("ok", "already_ok"):
                        summary = (
                            f"T={best['T_target']:.1f}°C, "
                            f"RH={best['RH_target']:.1f}%, "
                            f"ΔT={best['cooling_dT_C']:.1f}°C, "
                            f"{best['water_L_per_m2']:.3f} L/m²"
                        )


                        detail = {
                            "T_target": best.get("T_target"),
                            "RH_target": best.get("RH_target"),
                            "cooling_dT_C": best.get("cooling_dT_C"),
                            "water_L_per_m2": best.get("water_L_per_m2"),
                            "water_L_total": best.get("water_L_total"),
                            "q_sens_kWh_per_m2": best.get("q_sens_kWh_per_m2"),
                            "q_lat_kWh_per_m2": best.get("q_lat_kWh_per_m2"),
                            "q_tot_kWh_per_m2": best.get("q_tot_kWh_per_m2"),
                        }

                        save_vpd_solution_alarm(
                            time_str=time_str,
                            vpd=vpd_now,
                            temperature=T_now,
                            humidity=RH_now,
                            solution_summary=summary,
                            solution_detail=detail,
                        )
                        print(f"[VPD 솔루션] {time_str} 시점 솔루션 저장 완료.")
            else:
                print("[VPD] 마지막 행 T/RH에 NaN이 있어 솔루션 계산 생략")

        except Exception as e:
            print(f"[VPD 솔루션] 계산/저장 중 오류: {e}")

        # 9) runner_state 업데이트
        save_last_processed_measurement_id(max_id)
        print(
            f"배치 처리 완료 - {datetime.now(KST).strftime('%H:%M:%S')} (last_id={max_id})"
        )

        last_id = max_id
        time.sleep(interval_sec)


if __name__ == "__main__":
    main_loop(interval_sec=60, vpd_threshold=1.5)
