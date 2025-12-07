# rtdata.py
import streamlit as st
import sqlite3
import pandas as pd
import time
import numpy as np
import os
import json
from datetime import datetime
import pytz

KST = pytz.timezone("Asia/Seoul")

SENSOR_DB_PATH = "sensor_data.db"
SETTINGS_FILE = "config/settings.json"


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"t_location": 3, "h_location": 2, "r_location": 4}


def load_data():
    """sensor_data.db에서 최신 1000개 measurements 로드"""
    conn = sqlite3.connect(SENSOR_DB_PATH)
    query = "SELECT * FROM measurements ORDER BY id DESC LIMIT 1000"
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def insert_uploaded_data_to_db(df_up: pd.DataFrame):
    """
    업로드된 데이터프레임(df_up)을 measurements 테이블에 INSERT
    df_up 컬럼: time_str, temperature, humidity, irradiance 라고 가정
    """
    conn = sqlite3.connect(SENSOR_DB_PATH)
    cursor = conn.cursor()

    for _, row in df_up.iterrows():
        cursor.execute(
            """
            INSERT INTO measurements (time_str, temperature, humidity, irradiance, server_sent)
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                str(row["time_str"]),
                float(row["temperature"]) if pd.notna(row["temperature"]) else None,
                float(row["humidity"]) if pd.notna(row["humidity"]) else None,
                float(row["irradiance"]) if pd.notna(row["irradiance"]) else None,
            ),
        )

    conn.commit()
    conn.close()


@st.cache_data
def calculate_vpd(temperature, humidity):
    """VPD (kPa) 계산"""
    es = 0.6108 * np.exp((17.27 * temperature) / (temperature + 237.3))
    ea = es * (humidity / 100.0)
    vpd = es - ea
    return vpd


def show_rtdata():
    settings = load_settings()
    t_loc = settings.get("t_location", 3)
    h_loc = settings.get("h_location", 2)
    r_loc = settings.get("r_location", 4)

    st.title("🌿 실시간 데이터")
    st.markdown("---")

    # 1. 갱신 상태 관리 (alarms.py와 같은 패턴)
    if "rt_last_update" not in st.session_state:
        st.session_state.rt_last_update = 0
    if "rt_data" not in st.session_state:
        st.session_state.rt_data = pd.DataFrame()

    now_ts = time.time()

    # 60초 이상 지났으면 DB 재조회
    if now_ts - st.session_state.rt_last_update > 60:
        df = load_data()
        st.session_state.rt_data = df
        st.session_state.rt_last_update = now_ts
    else:
        df = st.session_state.rt_data

    # 2. 상단 갱신 시간 표시
    if st.session_state.rt_last_update > 0:
        dt_kst = datetime.fromtimestamp(st.session_state.rt_last_update, tz=KST)
        last_update_str = dt_kst.strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"마지막 갱신: {last_update_str} (자동: 60초 간격)")
    else:
        st.caption("초기 로딩 중...")

    # 3. 실시간 대시보드 표시
    if not df.empty:
        # server_sent 컬럼 숨기기
        if "server_sent" in df.columns:
            df = df.drop(columns=["server_sent"])

        latest = df.iloc[0]

        # KPI 영역
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric(label="🌡️ 온도", value=f"{latest['temperature']} °C")
        kpi2.metric(label="💧 습도", value=f"{latest['humidity']} %")
        kpi3.metric(label="☀️ 일사량", value=f"{latest['irradiance']:.2f} W/m²")

        temp_num = pd.to_numeric(latest["temperature"], errors="coerce")
        hum_num = pd.to_numeric(latest["humidity"], errors="coerce")
        if not pd.isna(temp_num) and not pd.isna(hum_num):
            current_vpd = calculate_vpd(temp_num, hum_num)
            kpi4.metric(label="💦 VPD", value=f"{current_vpd:.2f} kPa")
        else:
            kpi4.metric(label="💦 VPD", value="계산 불가")

        st.markdown(
            f"<div style='text-align:right; font-size:12px; color:#666;'>{latest['time_str']} 기준</div>",
            unsafe_allow_html=True,
        )

        # 그래프용 정렬
        df_chart = df.sort_values("id")

        df_chart["temperature_num"] = pd.to_numeric(
            df_chart["temperature"], errors="coerce"
        )
        df_chart["humidity_num"] = pd.to_numeric(
            df_chart["humidity"], errors="coerce"
        )
        df_chart["irradiance_num"] = pd.to_numeric(
            df_chart["irradiance"], errors="coerce"
        )

        df_chart["vpd_num"] = df_chart.apply(
            lambda row: calculate_vpd(row["temperature_num"], row["humidity_num"])
            if pd.notna(row["temperature_num"]) and pd.notna(row["humidity_num"])
            else np.nan,
            axis=1,
        )

        st.subheader("실시간 변화 그래프")
        tab1, tab2, tab3, tab4 = st.tabs(["온도", "습도", "일사량", "VPD"])

        with tab1:
            st.line_chart(df_chart, x="time_str", y="temperature_num")
        with tab2:
            st.line_chart(df_chart, x="time_str", y="humidity_num")
        with tab3:
            st.line_chart(df_chart, x="time_str", y="irradiance_num")
        with tab4:
            st.line_chart(df_chart, x="time_str", y="vpd_num")

        # 데이터 표
        df_display = df.copy()
        df_display["VPD(kPa)"] = df_chart["vpd_num"].round(2)
        with st.expander("상세 데이터 보기", expanded=True):
            st.dataframe(df_display, hide_index=True)
    else:
        st.info("sensor_data.db에 표시할 데이터가 없습니다.")

    # 4. 페이지 아래쪽: 과거 데이터 업로드 영역
    st.markdown("---")
    st.subheader("📤 과거 데이터 업로드 (초기 학습용)")

    st.caption(
        "이전 기간의 온도/습도/일사량 데이터를 업로드하면 "
        "sensor_data.db에 병합되어, 이후 하루 1번 자동 학습에 포함됩니다. "
        "업로드 파일의 열 위치는 settings.json의 t/h/r_location을 따릅니다."
    )

    upload_col1, upload_col2 = st.columns([2, 1])

    with upload_col1:
        uploaded_file = st.file_uploader(
            "데이터 파일 업로드",
            type=["xlsx", "csv"],
        )

    with upload_col2:
        st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)
        do_upload = st.button("업로드")

    if uploaded_file is not None and do_upload:
        try:
            # 1) 파일 읽기
            if uploaded_file.name.lower().endswith(".xlsx"):
                df_up_raw = pd.read_excel(uploaded_file, header=0)
            else:
                df_up_raw = pd.read_csv(uploaded_file, header=0)

            # 2) settings의 열 위치 기반 추출
            use_cols = [0, h_loc, r_loc, t_loc]  # [시간, 습도, 광, 온도]
            df_sub = df_up_raw.iloc[:, use_cols].copy()

            # 열 이름 재설정
            df_sub.columns = ["Timestamp", "Humidity", "Solar_Radiation", "Temperature"]

            # 3) 형 변환
            df_sub["Timestamp"] = pd.to_datetime(df_sub["Timestamp"], errors="coerce")
            df_sub["Humidity"] = pd.to_numeric(df_sub["Humidity"], errors="coerce")
            df_sub["Solar_Radiation"] = pd.to_numeric(
                df_sub["Solar_Radiation"], errors="coerce"
            )
            df_sub["Temperature"] = pd.to_numeric(
                df_sub["Temperature"], errors="coerce"
            )

            # 4) DB용 스키마로 변환
            df_for_db = pd.DataFrame(
                {
                    "time_str": df_sub["Timestamp"].dt.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "temperature": df_sub["Temperature"],
                    "humidity": df_sub["Humidity"],
                    "irradiance": df_sub["Solar_Radiation"],
                }
            ).dropna(subset=["time_str"])

            # 5) DB INSERT
            insert_uploaded_data_to_db(df_for_db)

            st.success(f"업로드 완료: {len(df_for_db)}건이 sensor_data.db에 추가되었습니다.")

        except Exception as e:
            st.error(f"업로드 처리 중 오류 발생: {e}")
    elif uploaded_file is None and do_upload:
        st.warning("먼저 업로드할 파일을 선택해 주세요.")
