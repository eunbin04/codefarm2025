# mediadata.py
import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = 'sensor_data.db'

def get_latest_data(limit=50):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        f"SELECT * FROM measurements ORDER BY id DESC LIMIT {limit}", conn
    )
    conn.close()
    return df

st.set_page_config(page_title='CODEFARM 센서 대시보드', page_icon=':seedling:')
st.title("🌡️ 온습도, 광 센서 데이터 실시간 보기")

# 최신 데이터를 주기적으로 새로고침
refresh_interval = st.sidebar.slider('새로고침 간격(초)', 2, 30, 5)
if st.button('새로고침'):
    st.experimental_rerun()

st.caption('최근 수집된 센서 데이터(최대 50건)')
data = get_latest_data(50)
st.dataframe(data)

# 시각화 (온도, 습도, 광량)
st.subheader('📊 데이터 그래프')
st.line_chart(data[['humidity', 'temperature', 'irradiance']])

# 주기적 자동 새로고침 (Streamlit 1.18+)
st.experimental_set_query_params()
st.write(f"데이터 건수: {len(data)}")

# 참고: Streamlit을 완전히 실시간으로 만들려면 st.empty와 time.sleep을 활용한 반복 루프도 응용 가능
