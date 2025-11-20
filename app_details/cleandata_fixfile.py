# cleandata_fixfile.py
import pandas as pd
import os
import sqlite3
from precleaning.incoding import read_csv_robust, clean_for_analysis
from outlier_fix.predict import correct_outlier, load_settings
from outlier_find.find_outlier import find_outlier

def upload_preclean(uploaded_file):
    if uploaded_file is not None:
        temp_path = f"temp/{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if uploaded_file.type == 'text/csv':
            df_raw, enc = read_csv_robust(temp_path)
            df_clean = clean_for_analysis(df_raw)
            enc_used = enc
        else:
            df_clean = pd.read_excel(temp_path)
            df_clean = clean_for_analysis(df_clean)
            enc_used = 'excel'

        conn = sqlite3.connect('codefarmdb.sqlite')
        df_clean.to_sql('farm_data', conn, if_exists='replace', index=False)
        conn.close()

        return temp_path, enc_used, df_clean.tail()
    else:
        return None, None, None

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
