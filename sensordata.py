import streamlit as st
import pandas as pd
import numpy as np
import datetime
import altair as alt

def show_sensordata():
    st.title("센서 데이터 (Sensor Data)")

    # 가상의 센서 데이터 생성 (최근 24시간, 1시간 단위)
    now = datetime.datetime.now()
    times = [now - datetime.timedelta(hours=i) for i in range(23, -1, -1)]

    data = {
        "시간": times,
        "온도(°C)": np.random.normal(loc=25, scale=2, size=24).round(1),
        "습도(%)": np.random.normal(loc=60, scale=5, size=24).round(1),
        "CO2(ppm)": np.random.normal(loc=400, scale=50, size=24).round(0),
    }

    df = pd.DataFrame(data)

    # 테이블 표시
    st.subheader("원본 센서 데이터")
    st.dataframe(df)

    # Altair로 시계열 그래프
    st.subheader("시간별 센서 데이터 그래프")

    base = alt.Chart(df).encode(x='시간:T')

    temp_line = base.mark_line(color='red').encode(y='온도(°C):Q')
    humid_line = base.mark_line(color='blue').encode(y='습도(%):Q')
    co2_line = base.mark_line(color='green').encode(y='CO2(ppm):Q')

    # 선택할 센서 타입 체크박스
    show_temp = st.checkbox("온도", value=True)
    show_humid = st.checkbox("습도", value=True
