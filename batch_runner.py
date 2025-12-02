# batch_runner.py
import sqlite3
import time
import pandas as pd
import os
import json
from datetime import datetime
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

    while True:
        if not alert_enabled:
            print("알림 비활성화 상태 - 5분 대기")
            time.sleep(300)
            continue

        df_new = load_new_sensor_data(last_id=last_id, batch_size=1000)

        if df_new.empty:
            time.sleep(interval_sec)
            continue

        max_id = int(df_new["id"].max())

        cleaned_df, alarm_df = find_outliers_and_mark(df_new, datetime_col="time_str")
        corrected_df, msg, target_sensor, predicted_value = correct_last_row_outlier(
            cleaned_df, settings=settings
        )

        # 알림 저장
        if not alarm_df.empty:
            insert_alarm_rows(alarm_df)
            print(f"알림 {len(alarm_df)}건 저장")

        # 보정내용/보정값 업데이트
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

        # 보정된 전체 데이터 저장
        save_corrected_sensor_data(corrected_df, settings=settings)

        save_last_processed_measurement_id(max_id)
        print(
            f"배치 처리 완료 - {datetime.now(KST).strftime('%H:%M:%S')} (last_id={max_id})"
        )

        last_id = max_id
        time.sleep(interval_sec)


if __name__ == "__main__":
    main_loop(interval_sec=60)
