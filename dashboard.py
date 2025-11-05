# dashboard.py
import streamlit as st
import pandas as pd

# 데이터 불러오기(priva)
def load_data():
    df = pd.read_csv('priva.csv', sep=';', decimal='.', header=0, encoding='utf-8')
    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], dayfirst=True, errors='coerce')
    df.set_index('Timestamp', inplace=True)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)
    return df

def show_dashboard():
    st.title(':seedling: 프리바 데이터')

    data = load_data()

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

    name_map = {
        'Meas CO2 Level': 'CO2',
        'Meas Rel Hum': '내부 습도',
        'Meas GH Temp': '온실 온도',
        'Meas Out Temp': '외부 온도',
        'Meas Light': '조도',
        'Irrig Flow': '관개 유량',
    }

    selected_vars = st.multiselect(
        '측정 변수 선택',
        options=data.columns.tolist(),
        format_func=lambda x: name_map.get(x, x),
        default=data.columns[:6].tolist()
    )

    if selected_vars:
        plot_data = filtered[selected_vars].copy()  # 필터링된 데이터 사용
        plot_data.columns = [name_map.get(col, col) for col in selected_vars]
        st.line_chart(plot_data)
    else:
        st.warning('적어도 하나 이상의 변수를 선택해 주세요.')


if __name__ == "__main__":
    show_dashboard()
