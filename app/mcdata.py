# mcdata.py
import streamlit as st
import pandas as pd

# 데이터 불러오기(mc.csv)
def load_mcdata():
    df = pd.read_csv('data/mc.csv', encoding='utf-8')

    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df.set_index('Timestamp', inplace=True)
    
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)

    df = df.round(3)

    return df


def show_mcdata():
    st.title('🌿 미기후 데이터')

    st.markdown("---")

    st.subheader("📅 기간별 데이터")

    data = load_mcdata()  # 전체 데이터 불러오기

    # 데이터가 있는 고유 날짜 리스트 생성
    available_dates = sorted(list(set(data.index.date)))
    
    # 최소, 최대 날짜 설정
    min_date = available_dates[0]
    max_date = available_dates[-1]

    # 사용자가 선택할 기본값: 전체 범위
    default_start = min_date
    default_end = max_date

    # 날짜 입력 받기 (달력 형태)
    date_range = st.date_input(
        "조회할 기간 선택",
        value=(default_start, default_end),
        min_value=min_date,
        max_value=max_date
    )

    # date_input에서 단일 날짜 선택 시를 대비해 튜플로 처리
    if isinstance(date_range, tuple) or isinstance(date_range, list):
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    # 날짜 범위에 맞게 데이터 필터링 (시간 포함 인덱스이므로 날짜 조건으로 필터)
    filtered = data.loc[(data.index.date >= start_date) & (data.index.date <= end_date)]

    filtered = filtered.dropna(axis=1, how='all')

    selected_vars = st.multiselect(
        '측정 변수 선택',
        options=filtered.columns.tolist(),
        default=filtered.columns[:6].tolist()
    )

    # 비어있는 열 제거 후 남은 컬럼 리스트에 맞게 selected_vars 필터링
    selected_vars = [var for var in selected_vars if var in filtered.columns]

    # 기간 내의 선택된 변수 전체 원본 데이터 CSV로 변환
    csv = filtered[selected_vars].to_csv().encode('utf-8')
    st.download_button(label=":material/download: CSV 다운로드", data=csv, file_name='sensor_data.csv', mime='text/csv')

    # 데이터 미리보기
    st.dataframe(filtered[selected_vars].head())

    st.markdown("---")

    st.subheader("📊 데이터 통계")
    # desc = filtered[selected_vars].describe().T[['mean', 'min', 'max']]
    # desc.columns = ['평균', '최소', '최대']
    st.dataframe(filtered[selected_vars].describe())
