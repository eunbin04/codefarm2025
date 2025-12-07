# batch_runner.py
import sqlite3
import time
import pandas as pd
import os
import json
from datetime import datetime, date
import pytz

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
)

from outlier_fix.train_models_rt import main as train_models_rt_main

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

def should_run_training_today(settings, last_train_date_str):
    """
    오늘 auto_train_time이 지났고, 아직 오늘은 학습 안 했으면 True
    """
    auto_time_str = settings.get("auto_train_time", "17:15")
    now = datetime.now(KST)

    # 오늘 날짜
    today = now.date()

    # 마지막 학습일
    if last_train_date_str:
        try:
            last_train_date = datetime.strptime(last_train_date_str, "%Y-%m-%d").date()
        except ValueError:
            last_train_date = None
    else:
        last_train_date = None

    # 이미 오늘 학습했으면 False
    if last_train_date == today:
        return False

    # auto_train_time (시:분)
    try:
        auto_hour, auto_minute = map(int, auto_time_str.split(":"))
    except Exception:
        auto_hour, auto_minute = 17, 15

    auto_run_dt = datetime(
        year=now.year, month=now.month, day=now.day,
        hour=auto_hour, minute=auto_minute, tzinfo=KST
    )

    # 현재 시각이 auto_run_dt 이후라면 오늘 학습해야 함
    return now >= auto_run_dt

def main_loop(interval_sec=60):
    initialize_alarms_db()

    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = load_settings()

    alert_enabled = settings.get("alert_enabled", True)
    print(f"시스템 시작 - 알림 활성화: {alert_enabled}")

    last_id = get_last_processed_measurement_id()

    # 오늘 학습 여부 체크용 (프로세스 기준)
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

        # 5) 알림 저장
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

        # 8) runner_state 업데이트
        save_last_processed_measurement_id(max_id)
        print(
            f"배치 처리 완료 - {datetime.now(KST).strftime('%H:%M:%S')} (last_id={max_id})"
        )

        last_id = max_id
        time.sleep(interval_sec)

if __name__ == "__main__":
    main_loop(interval_sec=60)
