# home.py
import streamlit as st
import sqlite3
import pandas as pd
import base64

def get_img_base64(path):
    with open(path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

img_base64 = get_img_base64("data/farm.jpg")


def get_latest_sensor():
    try:
        conn = sqlite3.connect("sensor_data.db")
        df = pd.read_sql("SELECT * FROM measurements ORDER BY id DESC LIMIT 1", conn)
        conn.close()
        if df.empty:
            return None
        return df.iloc[0]
    except:
        return None


def show_home():

    st.markdown(
        f"""
        <div style="
            width:100%;
            height:200px;
            background-image: url('data:image/jpg;base64,{img_base64}');
            background-size: cover;
            background-position: center;
            border-radius:10px;
            opacity:0.5;
            margin-bottom:20px;
        ">
        </div>
        """,
        unsafe_allow_html=True
    )


    farm = st.session_state.get("farm_name", "CODEFARM 온실")

    st.title(f"{farm}")

    st.markdown("---")

    # 1) 최신 데이터 표시(있으면)
    latest = get_latest_sensor()

    st.subheader("최신 농가 상태")

    if latest is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌡️ 온도", f"{latest['temperature']} ℃")
        c2.metric("💧 습도", f"{latest['humidity']} %")
        c3.metric("☀️ 광량", f"{latest['irradiance']} W/m²")
        c4.metric("⏱️ 측정 시각", latest["time_str"])

    else:
        st.info("아직 센서 데이터가 없습니다.\n데이터 업로드 또는 연결을 진행하세요.")


    st.markdown("---")
    st.subheader("주요 기능")

    st.markdown("##### 데이터 조회 및 분석")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🌿 실시간 데이터"):
            st.session_state['page'] = 'nowdata'

    with col2:
        if st.button("📅 기간별 분석"):
            st.session_state['page'] = 'perdata'

    with col3:
        if st.button("🛠️ 데이터 보정"):
            st.session_state['page'] = 'cleandata'


    st.markdown("##### 관리 기능")
    col4, col5, col6 = st.columns(3)

    with col4:
        if st.button("🚨 알림 기록"):
            st.session_state['page'] = 'alarms'

    with col5:
        if st.button("⛅ 기상 정보"):
            st.session_state['page'] = 'weather'

    with col6:
        if st.button("⚙️ 설정 페이지"):
            st.session_state['page'] = 'settings'


    st.markdown("---")