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

    # 1. 실시간 요약 (기존대로)
    korea_now = get_korea_time()
    base_time = (korea_now - timedelta(minutes=40)).strftime("%H00")
    base_date = korea_now.strftime("%Y%m%d")

    params_now = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    try:
        response = requests.get("http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst", params=params_now, timeout=10)
        response.raise_for_status()
        data = response.json()
        items = data["response"]["body"]["items"]["item"]
        df_now = pd.DataFrame(items)
        if df_now.empty:
            st.info('기상청에서 응답은 있으나 데이터가 없습니다.')
        else:
            df_pivot_now = df_now.pivot(index=["baseDate", "baseTime", "nx", "ny"], columns="category", values="obsrValue").reset_index()
            df_pivot_now["datetime"] = pd.to_datetime(df_pivot_now["baseDate"] + df_pivot_now["baseTime"], format="%Y%m%d%H%M")
            latest = df_pivot_now.sort_values("datetime").iloc[-1]

            t1h = float(latest.get("T1H", 0))
            reh = float(latest.get("REH", 0))
            rn1 = float(latest.get("RN1", 0))
            wsd = float(latest.get("WSD", 0))
            vec = float(latest.get("VEC", 0))
            pty = latest.get("PTY", '0')
            pty = int(pty) if str(pty).isdigit() else 0

            pty_desc = pty_to_desc(pty)
            wind_dir = deg_to_dir(vec)
            dt_str = latest["datetime"].strftime("%Y-%m-%d %H:%M")

            summary = (
                f"[{dt_str}]\n"
                f"- 기온: {t1h}℃\n"
                f"- 습도: {reh}%\n"
                f"- 강수: {pty_desc} (최근 1시간 {rn1}mm)\n"
                f"- 풍속: {wsd} m/s, 풍향: {wind_dir} ({vec}°)"
            )

            st.subheader("실시간 요약")
            st.markdown(summary)
    except Exception as e:
        st.error(f"기상청 API 데이터 조회 실패: {e}")
        return

    st.markdown("---")

    # 2. 다운로드용 날짜/시간 선택 및 데이터 조회
    st.subheader("날씨 데이터 다운로드")

    # 다운로드 날짜와 시간 선택 UI
    selected_date = st.date_input('다운로드 날짜 선택', value=korea_now.date())
    selected_hour = st.selectbox('다운로드 시간 선택 (정시 기준)', [f"{h:02d}00" for h in range(24)], index=(korea_now.hour - 1) % 24)

    base_date_dl = selected_date.strftime("%Y%m%d")
    base_time_dl = selected_hour

    params_dl = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date_dl,
        "base_time": base_time_dl,
        "nx": nx,
        "ny": ny,
    }

    try:
        response_dl = requests.get("http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst", params=params_dl, timeout=10)
        response_dl.raise_for_status()
        data_dl = response_dl.json()
        items_dl = data_dl["response"]["body"]["items"]["item"]
        df_dl = pd.DataFrame(items_dl)
        if df_dl.empty:
            st.info('선택한 시점에 데이터가 없습니다.')
            return
    except Exception as e:
        st.error(f"다운로드용 API 조회 실패: {e}")
        return

    df_pivot_dl = df_dl.pivot(index=["baseDate", "baseTime", "nx", "ny"], columns="category", values="obsrValue").reset_index()
    df_pivot_dl["datetime"] = pd.to_datetime(df_pivot_dl["baseDate"] + df_pivot_dl["baseTime"], format="%Y%m%d%H%M")
    st.dataframe(df_pivot_dl)

    csv = df_pivot_dl.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label=":material/download: CSV 파일",
        data=csv,
        file_name=f"ultra_short_weather_{base_date_dl}_{base_time_dl}.csv",
        mime="text/csv"
    )

    st.markdown("데이터 출처: 기상청 초단기실황 API")
