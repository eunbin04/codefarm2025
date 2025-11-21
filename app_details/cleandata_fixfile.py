# cleandata_fixfile.py
import pandas as pd
import os
import sqlite3
from precleaning.incoding import read_csv_robust, clean_for_analysis
from outlier_fix.predict import correct_outlier, load_settings
from outlier_find.find_outlier import find_outlier

def upload_preclean(uploaded_file):
    if uploaded_file is not None:
        path = f"{uploaded_file.name}"
        with open(path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if uploaded_file.type == 'text/csv':
            df_raw, enc = read_csv_robust(path)
            df_clean = clean_for_analysis(df_raw)
            enc_used = enc
        else:
            df_clean = pd.read_excel(path)
            df_clean = clean_for_analysis(df_clean)
            enc_used = 'excel'

        conn = sqlite3.connect('codefarmdb.sqlite')

        table_name = os.path.splitext(uploaded_file.name)[0]  # 파일명으로 테이블명 지정
        df_clean.to_sql(table_name, conn, if_exists='replace', index=False)

        conn.close()

        return path, enc_used, df_clean.tail()
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
    return df, df.tail()


def process_file(file_path):
    settings = load_settings()
    location_map = {
        settings['t_location']: 'Temperature',
        settings['h_location']: 'Humidity',
        settings['r_location']: 'Solar_Radiation'
    }
    outlier_path = f"temp/outlier_{os.path.basename(file_path)}"
    fixed_file = f"temp/fixed_{os.path.splitext(os.path.basename(file_path))[0]}.xlsx"
    find_outlier(file_path, output_path=outlier_path, location_map=location_map)
    msg = correct_outlier(input_path=outlier_path, output_path=fixed_file, settings=settings)
    return fixed_file, msg
