import streamlit as st
import pandas as pd
import math

# Set page config
st.set_page_config(page_title='환경 데이터 대시보드', page_icon=':seedling:')

@st.cache_data
def load_data():
    df = pd.read_csv('priva.csv', sep=';', decimal='.', skiprows=3, encoding='utf-8')
    # 날짜시간 변환
    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], dayfirst=True)
    df.set_index('Timestamp', inplace=True)
    # 숫자 변환 및 -32767 같은 이상치 처리
    df = df.apply(pd.to_numeric, errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)
    return df

data = load_data()

st.title(':seedling: 환경 모니터링 대시보드')

# 시간 범위 선택
min_time, max_time = data.index.min(), data.index.max()
time_range = st.slider(
    '데이터 시간 범위 선택',
    min_value=min_time,
    max_value=max_time,
    value=(min_time, max_time),
    format="YYYY-MM-DD HH:mm"
)

filtered = data.loc[time_range[0]:time_range[1]]

# 표시할 변수 선택
variables = filtered.columns.to_list()
selected_vars = st.multiselect('측정 변수 선택', variables, default=variables[:6])

# 시계열 차트
if selected_vars:
    st.line_chart(filtered[selected_vars])

    # 첫/마지막 시점 데이터와 증감률 출력
    st.header('기간 내 데이터 요약')
    cols = st.columns(4)
    first_row = filtered[selected_vars].iloc[0]
    last_row = filtered[selected_vars].iloc[-1]

    for i, var in enumerate(selected_vars):
        col = cols[i % 4]
        with col:
            start_val = first_row[var]
            end_val = last_row[var]
            if pd.isna(start_val) or start_val == 0 or pd.isna(end_val):
                diff_ratio = 'n/a'
            else:
                diff_ratio = f'{end_val / start_val:.2f}x'
            st.metric(label=var, value=f'{end_val:.2f}', delta=diff_ratio)
else:
    st.warning('적어도 하나 이상의 변수를 선택해 주세요.')
