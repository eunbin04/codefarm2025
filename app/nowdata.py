# nowdata.py
import streamlit as st
import sqlite3
import pandas as pd
import time

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

    # 화면을 계속 갱신하기 위한 빈 공간 만들기
    placeholder = st.empty()

    # 무한 반복하며 화면 갱신 (실시간 대시보드 느낌)
    while True:
        df = load_data()
        
        if not df.empty:
            latest = df.iloc[0]

            with placeholder.container():
                # 1. 상단 지표 (Metric) 표시
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric(label="🌡️ 온도", value=f"{latest['temperature']} °C")
                kpi2.metric(label="💧 습도", value=f"{latest['humidity']} %")
                kpi3.metric(label="☀️ 일사량", value=f"{latest['irradiance']} W/m²")

                # 2. 그래프 그리기 (최신순이라 그래프가 거꾸로 보일 수 있어 뒤집음)
                df_chart = df.sort_values('id') 
                
                st.subheader("실시간 변화 그래프")
                
                # 3가지 데이터를 탭으로 나누어 보여주기
                tab1, tab2, tab3 = st.tabs(["온도", "습도", "일사량"])
                
                with tab1:
                    st.line_chart(df_chart, x='time_str', y='temperature', color='#FF5733')
                with tab2:
                    st.line_chart(df_chart, x='time_str', y='humidity', color='#33C1FF')
                with tab3:
                    st.line_chart(df_chart, x='time_str', y='irradiance', color='#FFC300')

                # 3. 데이터 표 (원시 데이터)
                if {'server_sent'}.issubset(df.columns):
                     df = df.drop(columns=['server_sent'])
                with st.expander("상세 데이터 보기"):
                    st.dataframe(df)

        # 60초마다 갱신
        time.sleep(60)