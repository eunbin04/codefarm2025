# weather.py
import streamlit as st
import math
import requests
import pandas as pd
from datetime import datetime, timedelta
from utils import get_korea_time


def latlon_to_xy(lat, lon):
    RE = 6371.00877
    GRID = 5.0
    SLAT1 = 30.0
    SLAT2 = 60.0
    OLON = 126.0
    OLAT = 38.0
    XO = 43
    YO = 136
    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)
    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny

def pty_to_desc(pty):
    mapping = {0: "강수 없음", 1: "비", 2: "비/눈", 3: "눈", 5: "빗방울", 6: "빗방울/눈날림", 7: "눈날림"}
    return mapping.get(pty, f"코드 {pty}")

def deg_to_dir(deg):
    if pd.isna(deg):
        return "정보 없음"
    deg = float(deg) % 360
    dirs = [
        "북", "북북동", "북동", "동북동", "동",
        "동남동", "남동", "남남동", "남",
        "남남서", "남서", "서남서", "서",
        "서북서", "북서", "북북서"
    ]
    idx = int((deg + 11.25) // 22.5) % 16
    return dirs[idx]


def show_weather():
    st.title("⛅ 기상 정보")
    st.markdown("---")

    # 입력값: 위경도
    LAT = st.number_input('위도 (LAT)', value=36.1234, format="%.4f")
    LON = st.number_input('경도 (LON)', value=127.5678, format="%.4f")
    SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"


    nx, ny = latlon_to_xy(LAT, LON)
    # st.write(f"좌표: ({nx}, {ny})")

    # 발표 기준시각 (오늘, 40분 전 정시 기준)
    korea_now = get_korea_time()
    base_time = (korea_now - timedelta(minutes=40)).strftime("%H00")
    base_date = korea_now.strftime("%Y%m%d")

    # API 파라미터
    BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    # API 호출 및 에러 처리
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        items = data["response"]["body"]["items"]["item"]
        df = pd.DataFrame(items)
        if df.empty:
            st.info('기상청에서 응답은 있지만, 데이터가 없습니다.')
            return
    except Exception as e:
        st.error(f"기상청 API 데이터 조회 실패: {e}")
        return

    # 데이터 가공
    df_pivot = df.pivot(
        index=["baseDate", "baseTime", "nx", "ny"],
        columns="category",
        values="obsrValue"
    ).reset_index()
    df_pivot["datetime"] = pd.to_datetime(
        df_pivot["baseDate"] + df_pivot["baseTime"], format="%Y%m%d%H%M"
    )
    latest = df_pivot.sort_values("datetime").iloc[-1]

    def to_float(val):
        try:
            return float(val)
        except:
            return None

    t1h = to_float(latest.get("T1H"))
    reh = to_float(latest.get("REH"))
    rn1 = to_float(latest.get("RN1"))
    wsd = to_float(latest.get("WSD"))
    vec = to_float(latest.get("VEC"))
    pty = latest.get("PTY")
    pty = int(pty) if pty is not None and str(pty).isdigit() else 0

    pty_desc = pty_to_desc(pty)
    wind_dir = deg_to_dir(vec)
    dt_str = latest["datetime"].strftime("%Y-%m-%d %H:%M")

    # 요약 출력
    def summary(dt_str, t1h, reh, pty_desc, rn1, wsd, wind_dir, vec):
        st.subheader("실시간 요약")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                f"""
                <div style="border:1px solid #ddd; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:24px;">🌡️</div>
                    <div>기온</div>
                    <div style="font-weight:bold; font-size:18px;">{t1h}℃</div>
                </div>
                """, unsafe_allow_html=True)

        with col2:
            st.markdown(
                f"""
                <div style="border:1px solid #ddd; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:24px;">💧</div>
                    <div>습도</div>
                    <div style="font-weight:bold; font-size:18px;">{reh}%</div>
                </div>
                """, unsafe_allow_html=True)

        with col3:
            wind_deg = f" ({vec}°)" if vec is not None else ""
            st.markdown(
                f"""
                <div style="border:1px solid #ddd; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:24px;">💨</div>
                    <div>풍속/풍향</div>
                    <div style="font-weight:bold; font-size:18px;">{wsd} m/s / {wind_dir}{wind_deg}</div>
                </div>
                """, unsafe_allow_html=True)

        precipitation = f"{pty_desc}"
        if rn1 is not None and rn1 > 0:
            precipitation += f" (최근 1시간 {rn1}mm)"
        st.markdown(
            f"""
            <div style="
                border:2px solid #1E90FF; 
                border-radius:12px; 
                background-color:#E6F0FF; 
                padding:15px; 
                margin-top:20px; 
                text-align:center;
                font-size:20px;
                font-weight:bold;
                color:#1E90FF;
            ">
                ☔ 강수: {precipitation}
            </div>
            """, unsafe_allow_html=True)

        st.markdown(f"<div style='text-align:right; font-size:12px; color:#666;'>{dt_str} 기준</div>", unsafe_allow_html=True)
    

    st.subheader("실시간 요약")
    st.markdown(summary(dt_str, t1h, reh, pty_desc, rn1, wsd, wind_dir, vec))
    st.subheader("날씨 데이터 다운로드")
    st.dataframe(df_pivot)

    # CSV 다운로드 버튼
    csv = df_pivot.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label=":material/download: CSV 파일",
        data=csv,
        file_name="ultra_short_weather.csv",
        mime="text/csv"
    )

    st.markdown("---")
    st.markdown("데이터 출처: 기상청 초단기실황 API")