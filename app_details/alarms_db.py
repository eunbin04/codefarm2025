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

    # 이상치/결측 알림 테이블
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            alarm_type TEXT,
            value REAL,
            status TEXT,
            correction_status TEXT,
            correction_value REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # 보정된 센서 데이터
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

    # VPD 솔루션 알림 테이블
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vpd_alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            vpd REAL,
            temperature REAL,
            humidity REAL,
            solution_summary TEXT,
            solution_detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """이상치/결측 알림 목록 로드"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        query = """
            SELECT
                time_str,
                alarm_type,
                value,
                status,
                correction_status,
                correction_value
            FROM alarms
            ORDER BY created_at DESC
            LIMIT 200
        """
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty:
            return pd.DataFrame(
                columns=[
                    "수집일",
                    "알림 유형",
                    "실제 값",
                    "상태",
                    "보정내역",
                    "보정값",
                ]
            )

        df.columns = [
            "수집일",
            "알림 유형",
            "실제 값",
            "상태",
            "보정내역",
            "보정값",
        ]
        return df

    except Exception as e:
        st.error(f"알림 데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(
            columns=[
                "수집일",
                "알림 유형",
                "실제 값",
                "상태",
                "보정내역",
                "보정값",
            ]
        )


def save_alarm_to_db(alarm_data: dict):
    """단일 이상치/결측 알림 저장"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO alarms
            (time_str, alarm_type, value, status,
             correction_status, correction_value)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alarm_data.get("time_str", ""),
                alarm_data.get("alarm_type", ""),
                alarm_data.get("value", None),
                alarm_data.get("status", ""),
                alarm_data.get("correction_status", ""),
                alarm_data.get("correction_value", None),
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        st.error(f"알림 저장 중 오류 발생: {e}")
        return False


def insert_alarm_rows(alarm_df: pd.DataFrame):
    """find_outliers_and_mark에서 만든 alarm_df 저장"""
    for _, row in alarm_df.iterrows():
        save_alarm_to_db(
            {
                "time_str": row["time_str"],
                "alarm_type": row["alarm_type"],
                "value": row["value"],
                "status": row["status"],
                "correction_status": "",
                "correction_value": None,
            }
        )


def update_alarm_correction_with_value(
    time_str: str,
    alarm_type: str,
    correction_status: str,
    correction_value: float,
    correction_detail: str,
):
    """보정내역/보정값 업데이트"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE alarms
            SET correction_status = ?, correction_value = ?
            WHERE time_str = ? AND alarm_type = ?
            """,
            (correction_status, correction_value, time_str, alarm_type),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
    except Exception as e:
        st.error(f"알림 업데이트 중 오류 발생: {e}")
        return False


def save_corrected_sensor_data(corrected_df: pd.DataFrame, settings=None):
    """corrected_sensor 테이블 저장"""
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


def color_status(val, correction):
    if correction and correction != "":
        return "background-color: lightgreen;"
    return "background-color: lightcoral;"


# =========== VPD 솔루션용 함수 ===========


def save_vpd_solution_alarm(
    time_str: str,
    vpd: float,
    temperature: float,
    humidity: float,
    solution_summary: str,
    solution_detail: dict,
):
    """VPD 솔루션 발생 시 vpd_alarms에 저장"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO vpd_alarms
            (time_str, vpd, temperature, humidity, solution_summary, solution_detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                time_str,
                float(vpd) if vpd is not None else None,
                float(temperature) if temperature is not None else None,
                float(humidity) if humidity is not None else None,
                solution_summary,
                json.dumps(solution_detail, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"VPD 솔루션 알림 저장 중 오류 발생: {e}")
        return False


def load_vpd_solution_alarms(limit: int = 200) -> pd.DataFrame:
    """VPD 솔루션 알림 목록 로드"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        query = """
            SELECT
                time_str,
                vpd,
                temperature,
                humidity,
                solution_summary,
                solution_detail
            FROM vpd_alarms
            ORDER BY created_at DESC
            LIMIT ?
        """
        df = pd.read_sql(query, conn, params=(limit,))
        conn.close()

        if df.empty:
            return pd.DataFrame(
                columns=[
                    "시간",
                    "VPD",
                    "온도",
                    "습도",
                    "전략",
                    "상세",
                ]
            )

        df.columns = [
            "시간",
            "VPD",
            "온도",
            "습도",
            "전략",
            "상세",
        ]
        return df

    except Exception as e:
        st.error(f"VPD 솔루션 데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(
            columns=[
                "시간",
                "VPD",
                "온도",
                "습도",
                "전략",
                "상세",
            ]
        )
