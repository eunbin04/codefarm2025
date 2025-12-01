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
    update_alarm_correction,
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

        # 전체 df 중 가장 큰 id를 이번 배치의 마지막으로 기록
        max_id = int(df_new["id"].max())

        cleaned_df, alarm_df = find_outliers_and_mark(df_new, datetime_col="time_str")
        corrected_df, msg = correct_last_row_outlier(cleaned_df, settings=settings)

        if not alarm_df.empty:
            insert_alarm_rows(alarm_df)
            print(f"알림 {len(alarm_df)}건 저장")

        if msg != "보정할 이상치가 없습니다.":
            last_time_str = str(corrected_df.iloc[-1, 0])
            now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            correction_status = f"자동 보정 ({now_kst})"
            correction_detail = msg
            update_alarm_correction(last_time_str, correction_status, correction_detail)
            print(f"보정 완료: {msg}")

        save_corrected_sensor_data(corrected_df, settings=settings)

        save_last_processed_measurement_id(max_id)
        print(f"배치 처리 완료 - {datetime.now(KST).strftime('%H:%M:%S')} (last_id={max_id})")

        last_id = max_id
        time.sleep(interval_sec)


if __name__ == "__main__":
    main_loop(interval_sec=60)
