# app_details/cleandata_fixfile.py
import pandas as pd
import io
import os
import sqlite3
import chardet
from precleaning.incoding import read_csv_robust, clean_for_analysis
from outlier_find.find_full import find_outlier_df

def upload_preclean(uploaded_file, save_to_db=True, timestamp_col=None):
    """타임스탬프 메타데이터 저장 (화면에 숨김)"""
    if uploaded_file is None:
        return None, None, None

    original_name = os.path.splitext(uploaded_file.name)[0]
    content = uploaded_file.getbuffer()
    content_bytes = bytes(content)

    detected = chardet.detect(content_bytes)
    enc_guess = detected.get("encoding")

    if uploaded_file.type == "text/csv":
        df_raw, enc_detected = read_csv_robust(
            io.BytesIO(content_bytes),
            preferred_encoding=enc_guess,
        )
        df_clean = clean_for_analysis(df_raw)
        enc_used = enc_detected
    else:
        df_clean = pd.read_excel(io.BytesIO(content_bytes))
        df_clean = clean_for_analysis(df_clean)
        enc_used = "excel"

    table_name = None

    if save_to_db:
        conn = sqlite3.connect("codefarmdb.sqlite")
        cursor = conn.cursor()

        # 🔴 table_metadata 자동 생성 (숨김)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_metadata (
                table_name TEXT PRIMARY KEY,
                timestamp_col TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]

        table_name = original_name
        count = 1
        while table_name in existing_tables:
            table_name = f"{original_name}({count})"
            count += 1

        df_clean.to_sql(table_name, conn, if_exists="replace", index=False)
        
        # 🔴 타임스탬프 정보 저장 (메타데이터는 백그라운드에서만)
        if timestamp_col and timestamp_col in df_clean.columns:
            cursor.execute(
                "INSERT OR REPLACE INTO table_metadata (table_name, timestamp_col) VALUES (?, ?)",
                (table_name, timestamp_col)
            )
        conn.commit()
        conn.close()

    return table_name, enc_used, df_clean.head()

def get_table_list(db_path='codefarmdb.sqlite'):
    """메인 테이블만 반환 (table_metadata 숨김)"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name != 'table_metadata'
    """)
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

def export_table_to_df(table_name, db_path='codefarmdb.sqlite'):
    """안전한 타임스탬프 조회 (table_metadata 자동 생성)"""
    conn = sqlite3.connect(db_path)
    
    try:
        # 데이터 로드
        df = pd.read_sql(f"SELECT * FROM [{table_name}];", conn)
        
        # 🔴 table_metadata 안전 생성
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_metadata (
                table_name TEXT PRIMARY KEY,
                timestamp_col TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 안전한 타임스탬프 조회
        cursor.execute(
            "SELECT timestamp_col FROM table_metadata WHERE table_name = ?", 
            (table_name,)
        )
        result = cursor.fetchone()
        timestamp_col = result[0] if result else None
        
        conn.commit()
    except Exception:
        # 에러 시 첫 번째 컬럼 반환
        timestamp_col = df.columns[0] if len(df.columns) > 0 else None
    finally:
        conn.close()
    
    return df, df.head(), timestamp_col

def process_table_df(df, temp_index, humi_index, light_index, timestamp_index=None):
    from outlier_fix.predict_full import correct_outlier_df
    df_found = find_outlier_df(df, temp_index, humi_index, light_index, timestamp_index)
    df_fixed, msg = correct_outlier_df(df_found, temp_index, humi_index, light_index)
    return df_fixed, msg
