# alarms_db.py
import pandas as pd
import sqlite3
import json
import os
import streamlit as st
from datetime import datetime
import pytz

ALARMS_DB_PATH = "alarms.db"
SETTINGS_FILE = "config/settings.json"

KST = pytz.timezone("Asia/Seoul")


def get_korea_time():
    return datetime.now(KST)


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"t_location": 3, "h_location": 2, "r_location": 4}


def initialize_alarms_db():
    conn = sqlite3.connect(ALARMS_DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            alarm_type TEXT,
            status TEXT,
            correction_status TEXT,
            correction_detail TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS corrected_sensor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            humidity REAL,
            temperature REAL,
            irradiance REAL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # 증분 처리 상태 저장용
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS runner_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_processed_measurement_id INTEGER
        )
        """
    )

    conn.commit()
    conn.close()


def get_last_processed_measurement_id():
    conn = sqlite3.connect(ALARMS_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_processed_measurement_id FROM runner_state WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def save_last_processed_measurement_id(last_id: int):
    conn = sqlite3.connect(ALARMS_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO runner_state (id, last_processed_measurement_id)
        VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET last_processed_measurement_id = excluded.last_processed_measurement_id
        """,
        (last_id,),
    )
    conn.commit()
    conn.close()


def load_alarm_data_from_db():
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        query = """
            SELECT
                time_str,
                alarm_type,
                status,
                correction_status,
                correction_detail,
                description,
                datetime(created_at, 'localtime') AS created_at_kst
            FROM alarms
            ORDER BY created_at DESC
            LIMIT 100
        """
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty:
            return pd.DataFrame(
                columns=[
                    "시간",
                    "알림 유형",
                    "상태",
                    "보정내역",
                    "보정상세",
                    "설명",
                    "생성시각(KST)",
                ]
            )

        df.columns = [
            "시간",
            "알림 유형",
            "상태",
            "보정내역",
            "보정상세",
            "설명",
            "생성시각(KST)",
        ]
        return df

    except Exception as e:
        st.error(f"알림 데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(
            columns=[
                "시간",
                "알림 유형",
                "상태",
                "보정내역",
                "보정상세",
                "설명",
                "생성시각(KST)",
            ]
        )


def save_alarm_to_db(alarm_data: dict):
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO alarms
            (time_str, alarm_type, status, correction_status, correction_detail, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alarm_data.get("time_str", ""),
                alarm_data.get("alarm_type", ""),
                alarm_data.get("status", ""),
                alarm_data.get("correction_status", ""),
                alarm_data.get("correction_detail", ""),
                alarm_data.get("description", ""),
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        st.error(f"알림 저장 중 오류 발생: {e}")
        return False


def update_alarm_correction(time_str: str, correction_status: str, correction_detail: str):
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE alarms
            SET correction_status = ?, correction_detail = ?
            WHERE time_str = ?
            """,
            (correction_status, correction_detail, time_str),
        )

        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    except Exception as e:
        st.error(f"알림 업데이트 중 오류 발생: {e}")
        return False


def save_corrected_sensor_data(corrected_df: pd.DataFrame, settings=None):
    if settings is None:
        settings = load_settings()

    h_loc = settings.get("h_location", 2)
    r_loc = settings.get("r_location", 4)
    t_loc = settings.get("t_location", 3)

    cols = corrected_df.columns.tolist()
    time_col = cols[0]
    hum_col = cols[h_loc]
    rad_col = cols[r_loc]
    tmp_col = cols[t_loc]

    conn = sqlite3.connect(ALARMS_DB_PATH)
    cursor = conn.cursor()

    for _, row in corrected_df.iterrows():
        cursor.execute(
            """
            INSERT INTO corrected_sensor
            (time_str, humidity, temperature, irradiance, source, created_at)
            VALUES (?, ?, ?, ?, 'corrected', CURRENT_TIMESTAMP)
            """,
            (
                str(row[time_col]),
                float(row[hum_col]) if pd.notna(row[hum_col]) else None,
                float(row[tmp_col]) if pd.notna(row[tmp_col]) else None,
                float(row[rad_col]) if pd.notna(row[rad_col]) else None,
            ),
        )

    conn.commit()
    conn.close()
    return True


def insert_alarm_rows(alarm_df: pd.DataFrame):
    for _, row in alarm_df.iterrows():
        save_alarm_to_db(
            {
                "time_str": row["시간"],
                "alarm_type": row["알림 유형"],
                "status": row["상태"],
                "correction_status": "",
                "correction_detail": "",
                "description": row["설명"],
            }
        )


def color_status(val, correction):
    if correction and correction != "":
        return "background-color: lightgreen;"
    return "background-color: lightcoral;"