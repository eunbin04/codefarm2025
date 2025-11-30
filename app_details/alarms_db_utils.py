# alarms_db_utils.py
import sqlite3

ALARMS_DB_PATH = "alarms.db"


def init_alarms_db():
    """alarms.db에 alarms / corrected_sensor 테이블 생성"""
    conn = sqlite3.connect(ALARMS_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
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
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS corrected_sensor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            humidity REAL,
            temperature REAL,
            irradiance REAL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def insert_alarm_rows(alarm_df):
    """find_outliers_and_mark가 만든 alarm_df를 alarms 테이블에 INSERT"""
    if alarm_df.empty:
        return

    conn = sqlite3.connect(ALARMS_DB_PATH)
    cur = conn.cursor()

    sql = """
        INSERT INTO alarms
        (time_str, alarm_type, status, correction_status, correction_detail, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """

    rows = []
    for _, row in alarm_df.iterrows():
        rows.append((
            row["시간"],
            row["알림 유형"],
            row["상태"],
            "",                # 처음엔 미보정
            "",                # 보정 상세는 나중에 predict msg로 채움
            row.get("설명", ""),  # 이상치 설명
        ))

    cur.executemany(sql, rows)
    conn.commit()
    conn.close()


def update_alarm_with_correction(time_str, correction_status, correction_detail):
    """predict.py msg로 보정 상태/상세를 업데이트"""
    conn = sqlite3.connect(ALARMS_DB_PATH)
    cur = conn.cursor()

    sql = """
        UPDATE alarms
        SET correction_status = ?, correction_detail = ?
        WHERE time_str = ?
    """
    cur.execute(sql, (correction_status, correction_detail, time_str))
    conn.commit()
    conn.close()


def insert_corrected_rows(corrected_df, t_idx, h_idx, r_idx):
    """보정된 cleaned_df 전체(또는 마지막 행)를 corrected_sensor에 넣기"""
    if corrected_df.empty:
        return

    cols = corrected_df.columns.tolist()
    time_col = cols[0]
    t_col = cols[t_idx]
    h_col = cols[h_idx]
    r_col = cols[r_idx]

    conn = sqlite3.connect(ALARMS_DB_PATH)
    cur = conn.cursor()

    sql = """
        INSERT INTO corrected_sensor
        (time_str, humidity, temperature, irradiance, source, created_at)
        VALUES (?, ?, ?, ?, 'corrected', CURRENT_TIMESTAMP)
    """

    rows = []
    for _, row in corrected_df.iterrows():
        rows.append((
            str(row[time_col]),
            float(row[h_col]) if row[h_col] == row[h_col] else None,  # NaN 체크
            float(row[t_col]) if row[t_col] == row[t_col] else None,
            float(row[r_col]) if row[r_col] == row[r_col] else None,
        ))

    cur.executemany(sql, rows)
    conn.commit()
    conn.close()
