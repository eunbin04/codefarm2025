import streamlit as st
import sqlite3
import pandas as pd
import time
import numpy as np

def show_nowdata():

    st.title("🌿 실시간 데이터")
    st.markdown("---")

    # DB에서 데이터 가져오는 함수
    def load_data():
        conn = sqlite3.connect('sensor_data.db')
        # 최신 데이터 1000개만 가져오기 (데이터가 많아지면 느려지므로 제한)
        query = "SELECT * FROM measurements ORDER BY id DESC LIMIT 1000"
        df = pd.read_sql(query, conn)
        conn.close()
        return df

    # VPD 계산 함수 (온도, 습도 기반) - kPa 단위로 수정
    @st.cache_data
    def calculate_vpd(temperature, humidity):
        """VPD (kPa) 계산: 포화증기압 - 실제증기압"""
        # 포화증기압 (Tetens 공식, Tetens equation)
        es = 0.6108 * np.exp((17.27 * temperature) / (temperature + 237.3))
        # 실제증기압
        ea = es * (humidity / 100.0)
        # VPD (kPa 단위)
        vpd = es - ea
        return vpd

    # 화면을 계속 갱신하기 위한 빈 공간 만들기
    placeholder = st.empty()

    # 무한 반복하며 화면 갱신 (실시간 대시보드 느낌)
    while True:
        df = load_data()

        if not df.empty:
            # server_sent 컬럼은 시각화 전에 제거 (표, 그래프 모두에서 숨김)
            if 'server_sent' in df.columns:
                df = df.drop(columns=['server_sent'])

            latest = df.iloc[0]

            with placeholder.container():
                # 1. 상단 지표 (Metric) 표시 - VPD kPa 단위로 수정
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric(label="🌡️ 온도", value=f"{latest['temperature']} °C")
                kpi2.metric(label="💧 습도", value=f"{latest['humidity']} %")
                kpi3.metric(label="☀️ 일사량", value=f"{latest['irradiance']:.2f} W/m²")
                
                # 실시간 VPD 계산 및 표시 (kPa)
                temp_num = pd.to_numeric(latest['temperature'], errors='coerce')
                hum_num = pd.to_numeric(latest['humidity'], errors='coerce')
                if not pd.isna(temp_num) and not pd.isna(hum_num):
                    current_vpd = calculate_vpd(temp_num, hum_num)
                    kpi4.metric(label="💦 VPD", value=f"{current_vpd:.2f} kPa")
                else:
                    kpi4.metric(label="💦 VPD", value="계산 불가")

                st.markdown(
                    f"<div style='text-align:right; font-size:12px; color:#666;'>{latest['time_str']} 기준</div>",
                    unsafe_allow_html=True
                )

                # 2. 그래프 그리기 (최신순이라 그래프가 거꾸로 보일 수 있어 뒤집음)
                df_chart = df.sort_values('id')

                # 그래프용 숫자 컬럼 생성: "NaN" 같은 문자열은 NaN(결측)으로 처리 → 선이 끊겨 보임
                df_chart['temperature_num'] = pd.to_numeric(df_chart['temperature'], errors='coerce')
                df_chart['humidity_num'] = pd.to_numeric(df_chart['humidity'], errors='coerce')
                df_chart['irradiance_num'] = pd.to_numeric(df_chart['irradiance'], errors='coerce')
                
                # VPD 컬럼 추가 (kPa 단위로 동적 계산)
                df_chart['vpd_num'] = df_chart.apply(
                    lambda row: calculate_vpd(row['temperature_num'], row['humidity_num']) 
                    if pd.notna(row['temperature_num']) and pd.notna(row['humidity_num']) 
                    else np.nan, axis=1
                )

                st.subheader("실시간 변화 그래프")

                # 4가지 데이터를 탭으로 나누어 보여주기 (VPD 탭 추가)
                tab1, tab2, tab3, tab4 = st.tabs(["온도", "습도", "일사량", "VPD"])

                with tab1:
                    st.line_chart(df_chart, x='time_str', y='temperature_num')
                with tab2:
                    st.line_chart(df_chart, x='time_str', y='humidity_num')
                with tab3:
                    st.line_chart(df_chart, x='time_str', y='irradiance_num')
                with tab4:
                    st.line_chart(df_chart, x='time_str', y='vpd_num')

                # 3. 데이터 표
                df_display = df.copy()
                df_display['VPD(kPa)'] = df_chart['vpd_num'].round(2)
                with st.expander("상세 데이터 보기", expanded=True):
                    st.dataframe(df_display)

        # 60초마다 갱신
        time.sleep(60)
