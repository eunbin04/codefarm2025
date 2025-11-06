# sensordata.py
import streamlit as st
import pandas as pd
from datetime import timedelta

# 데이터 불러오기(mc.csv)
def load_data(limit_recent_day=True):
    df = pd.read_csv('data/mc.csv', encoding='utf-8')
    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df.set_index('Timestamp', inplace=True)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)

    if limit_recent_day:
        # 최근 하루 데이터만 필터링
        max_time = df.index.max()
        min_time = max_time - timedelta(days=1)
        df = df.loc[min_time:max_time]

    return df


def show_mcdata():
    st.title(':seedling: 온실 환경 관리')

    data = load_data(limit_recent_day=True)

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

    selected_vars = st.multiselect(
        '측정 변수 선택',
        options=data.columns.tolist(),
        default=data.columns[:6].tolist()
    )

    if selected_vars:
        plot_data = filtered[selected_vars].copy()
        st.line_chart(plot_data)
    else:
        st.warning('적어도 하나 이상의 변수를 선택해 주세요.')

    st.markdown("---")

    st.subheader("💾 데이터 다운로드")
    csv = filtered[selected_vars].to_csv().encode('utf-8')
    st.download_button(label="CSV 다운로드", data=csv, file_name='sensor_data.csv', mime='text/csv')

    st.markdown("---")

    st.subheader("📊 통계 요약")
    desc = filtered[selected_vars].describe().T[['mean', 'min', 'max']]
    desc.columns = ['평균', '최소', '최대']
    st.table(desc.style.format("{:.2f}"))



def show_mediadata():
    st.title(':herb: 배지 정보 모니터링')

    data = load_data(limit_recent_day=True)

    min_time = data.index.min().to_pydatetime()
    max_time = data.index.max().to_pydatetime()

    time_range = st.slider(
        '데이터 시간 범위 선택',
        min_value=min_time,
        max_value=max_time,
        value=(min_time, max_time),
        format="YYYY-MM-DD HH:mm",
        key='media_time_slider'
    )

    filtered = data.loc[time_range[0]:time_range[1]]

    selected_vars = st.multiselect(
        '배지 정보 변수 선택',
        options=data.columns.tolist(),
        default=data.columns[6:12].tolist()
    )

    if selected_vars:
        plot_data = filtered[selected_vars].copy()
        st.line_chart(plot_data)
    else:
        st.warning('적어도 하나 이상의 변수를 선택해 주세요.')

    st.markdown("---")

    st.subheader("💾 데이터 다운로드")
    csv = filtered[selected_vars].to_csv().encode('utf-8')
    st.download_button(label="CSV 다운로드", data=csv, file_name='media_data.csv', mime='text/csv')

    st.markdown("---")

    st.subheader("📊 통계 요약")
    desc = filtered[selected_vars].describe().T[['mean', 'min', 'max']]
    desc.columns = ['평균', '최소', '최대']
    st.table(desc.style.format("{:.2f}"))