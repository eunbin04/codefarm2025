# mediadata.py
import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = 'sensor_data.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            humidity REAL,
            temperature REAL,
            irradiance REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def get_latest_data(limit=50):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        f"SELECT * FROM measurements ORDER BY id DESC LIMIT {limit}", conn
    )
    conn.close()
    return df

st.set_page_config(page_title='CODEFARM 센서 대시보드', page_icon=':seedling:')
st.title("🌡️ 온습도, 광 센서 데이터 실시간 보기")

refresh_interval = st.slider('새로고침 간격(초)', 2, 30, 5)
if st.button('새로고침'):
    st.experimental_rerun()

st.caption('최근 수집된 센서 데이터(최대 50건)')
data = get_latest_data(50)
st.dataframe(data)

st.subheader('📊 데이터 그래프')
st.line_chart(data[['humidity', 'temperature', 'irradiance']])

st.experimental_set_query_params()
st.write(f"데이터 건수: {len(data)}")
