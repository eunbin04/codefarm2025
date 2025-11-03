import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title='CODEFARM', page_icon=':seedling:')

# 데이터 불러오기(priva)
def load_data():
    df = pd.read_csv('priva.csv', sep=';', decimal='.', header=0, encoding='utf-8')
       # 시간 열만 3번째 행부터 별도로 추출
    timestamp = pd.read_csv('priva.csv', sep=';', decimal='.', header=None, encoding='utf-8', skiprows=3, usecols=[0])
    # 날짜 변환
    timestamp = pd.to_datetime(timestamp[0], dayfirst=True, errors='coerce')
    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = timestamp
    df = df[~df['Timestamp'].isna()]
    df.set_index('Timestamp', inplace=True)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)

    return df
    
data = load_data()

st.title(':seedling: 환경 모니터링 대시보드')

min_time = data.index.min().to_pydatetime()  
max_time = data.index.max().to_pydatetime()

time_range = st.slider(
    '데이터 시간 범위 선택',
    min_value=min_time,
    max_value=max_time,
    value=(min_time, max_time),
    format="YYYY-MM-DD HH:mm",
    key='time_slider'
)

filtered = data.loc[time_range[0]:time_range[1]]

# 컬럼명 맵핑
name_map = {
    'Meas CO2 Level': 'CO2',
    'Meas Rel Hum': '내부 습도',
    'Meas GH Temp': '온실 온도',
    'Meas Out Temp': '외부 온도',
    'Meas Light': '조도',
    'Irrig Flow': '관개 유량',
}

mapped_columns = [name_map.get(col, col) for col in filtered.columns]

selected_vars = st.multiselect(
    '측정 변수 선택',
    options=data.columns.tolist(),
    format_func=lambda x: name_map.get(x, x),
    default=data.columns[:6].tolist()
)

if selected_vars:
    mapped_cols = [name_map.get(col, col) for col in selected_vars]
    plot_data = data[selected_vars].copy()
    plot_data.columns = mapped_cols
    st.line_chart(plot_data)
else:
    st.warning('적어도 하나 이상의 변수를 선택해 주세요.')