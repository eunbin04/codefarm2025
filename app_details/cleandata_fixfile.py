# cleandata_fixfile.py
import pandas as pd
import io
import os
import sqlite3
import chardet
from precleaning.incoding import read_csv_robust, clean_for_analysis


def upload_preclean(uploaded_file):
    if uploaded_file is not None:

        original_name = os.path.splitext(uploaded_file.name)[0]

        conn = sqlite3.connect('codefarmdb.sqlite')
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]

        table_name = original_name
        count = 1
        while table_name in existing_tables:
            table_name = f"{original_name}({count})"
            count += 1

        content = uploaded_file.getbuffer()

        content_bytes = bytes(content)
        detected = chardet.detect(content_bytes)
        enc_guess = detected.get("encoding")

        if uploaded_file.type == 'text/csv':
            df_raw, enc_detected = read_csv_robust(io.BytesIO(content), preferred_encoding=enc_guess)
            df_clean = clean_for_analysis(df_raw)
            enc_used = enc_detected
        else:
            df_clean = pd.read_excel(io.BytesIO(content))
            df_clean = clean_for_analysis(df_clean)
            enc_used = 'excel'

        df_clean.to_sql(table_name, conn, if_exists='replace', index=False)
        conn.close()

        return table_name, enc_used, df_clean.head()

    else:
        return None, None, None



def get_table_list(db_path='codefarmdb.sqlite'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

def export_table_to_df(table_name, db_path='codefarmdb.sqlite'):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(f"SELECT * FROM [{table_name}];", conn)
    conn.close()
    return df, df.head()

def process_table_df(df, temp_index, humi_index, light_index):
    from outlier_find.find_full import find_outlier_df
    from outlier_fix.predict_full import correct_outlier_df
    # 이상치 탐지 (index별로)
    df_found = find_outlier_df(df, temp_index, humi_index, light_index)
    # 이상치 보정 (index별로)
    df_fixed, msg = correct_outlier_df(df_found, temp_index, humi_index, light_index)
    return df_fixed, msg
