import streamlit as st
import pandas as pd
from datetime import datetime

# 데이터 불러오기 예제 (priva.csv 등)
def load_data():
    df = pd.read_csv('priva.csv', sep=';', decimal='.', skiprows=3, encoding='utf-8')
    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], dayfirst=True)
    df.set_index('Timestamp', inplace=True)
    df = df.apply(pd.to_numeric, errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)
    return df

data = load_data()

min_time = data.index.min().to_pydatetime()  # pandas Timestamp -> datetime.datetime 변환
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

selected_vars = st.multiselect('측정 변수 선택', filtered.columns.tolist(), default=filtered.columns[:6].tolist())

if selected_vars:
    st.line_chart(filtered[selected_vars])
else:
    st.warning('적어도 하나 이상의 변수를 선택해 주세요.')
