# batch_runner.py
import sqlite3
import time
import pandas as pd
import os, json
from outlier_find.find import find_outliers_and_mark
from outlier_fix.predict import correct_last_row_outlier
from app_details.alarms_db_utils import (
    init_alarms_db,
    insert_alarm_rows,
    update_alarm_with_correction,
    insert_corrected_rows,
)

SENSOR_DB_PATH = "sensor_data.db"  # 원본 센서 DB


def load_recent_sensor_data(limit=1000):
    """sensor_data.db에서 최근 데이터 일부를 읽어옴"""
    conn = sqlite3.connect(SENSOR_DB_PATH)
    query = """
        SELECT * FROM measurements
        ORDER BY id DESC
        LIMIT ?
    """
    df = pd.read_sql(query, conn, params=(limit,))
    conn.close()
    # 최신순으로 읽었으니, 시간 순 정렬
    df = df.sort_values("id")
    return df


def main_loop(interval_sec=60):
    # alarms.db 테이블 생성
    init_alarms_db()

    SETTINGS_FILE = "config/settings.json"

    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {"t_location": 1, "h_location": 3, "r_location": 4}

    t_idx = settings["t_location"]
    h_idx = settings["h_location"]
    r_idx = settings["r_location"]

    while True:
        # 1. sensor_data에서 최근 데이터 읽기
        df = load_recent_sensor_data(limit=1000)
        if df.empty:
            time.sleep(interval_sec)
            continue

        # 2. 이상치 탐지 + NaN 마킹 + alarm_df 생성
        cleaned_df, alarm_df = find_outliers_and_mark(df, datetime_col="time_str")

        # 3. 자동 보정 (마지막 행 기준)
        corrected_df, msg = correct_last_row_outlier(cleaned_df, settings=settings)

        # 4. alarms.db에 알림 로그 쌓기
        if not alarm_df.empty:
            insert_alarm_rows(alarm_df)

        # 5. alarms.db에 보정 상세(msg) 반영
        if msg != "보정할 이상치가 없습니다.":
            # 마지막 행의 time_str
            last_time_str = str(corrected_df.iloc[-1, 0])  # 0번 컬럼: time_str
            correction_status = f"자동 보정 ({time.strftime('%Y-%m-%d %H:%M:%S')})"
            correction_detail = msg
            update_alarm_with_correction(last_time_str, correction_status, correction_detail)

        # 6. corrected_sensor 테이블에 보정 결과 저장
        insert_corrected_rows(corrected_df, t_idx=t_idx, h_idx=h_idx, r_idx=r_idx)

        # 7. 다음 루프까지 대기
        time.sleep(interval_sec)


if __name__ == "__main__":
    # 20초마다 실행
    main_loop(interval_sec=20)
