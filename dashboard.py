import streamlit as st
import math
import requests
from datetime import datetime, timedelta

def calc_vpd(temp_c, rh):
    svp = 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    vpd = svp * (1 - rh / 100)
    return round(vpd, 3)

def get_weather_kma(nx, ny):
    service_key = "YOUR_SERVICE_KEY"  # 기상청 API 키

    now = datetime.now() - timedelta(hours=1)
    base_date = now.strftime("%Y%m%d")
    base_time = now.strftime("%H00")

    url = (
        f"http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"
        f"?serviceKey={service_key}&numOfRows=60&pageNo=1&dataType=json"
        f"&base_date={base_date}&base_time={base_time}&nx={nx}&ny={ny}"
    )

    response = requests.get(url)
    data = response.json()

    temp = None
    reh = None
    if data.get("response") and data["response"]["header"]["resultCode"] == "00":
        items = data["response"]["body"]["items"]["item"]
        for item in items:
            if item["category"] == "T1H":
                temp = float(item["fcstValue"])
            elif item["category"] == "REH":
                reh = float(item["fcstValue"])
        return temp, reh
    else:
        return None, None

def show_dashboard():
    st.title("📈 대시보드")

    # 지역명-격자 좌표 사전
    region_coords = {
        "서울": (60, 127),
        "부산": (98, 74),
        "대구": (89, 90)
    }

    region = st.selectbox("지역을 선택하세요", list(region_coords.keys()))

    if st.button("날씨 불러오기"):
        nx, ny = region_coords[region]
        temp, rh = get_weather_kma(nx, ny)
        if temp is not None and rh is not None:
            st.success(f"{region} 현재 온도: {temp}°C, 상대습도: {rh}%")
            vpd = calc_vpd(temp, rh)
            st.metric(label="VPD 증기압 결핍", value=f"{vpd} kPa")
            if 0.8 <= vpd <= 1.2:
                st.success("이상적인 VPD 범위(생육 촉진 구간)입니다.")
            elif 1.2 < vpd <= 1.5:
                st.warning("개화단계에 적합한 VPD 범위입니다.")
            else:
                st.error("비이상적 VPD입니다. 환경 조정 필요!")
        else:
            st.error("기상청 API에서 데이터를 가져오지 못했습니다.")

    st.markdown("""
    <details>
    <summary><b>몰리에 선도 설명</b></summary>
    식물의 생장 최적 구간: VPD 0.8~1.2 kPa<br>
    개화단계 적합: VPD 1.2~1.5 kPa<br>
    광합성 최적: VPD 0.45~1.136 kPa
    </details>
    """, unsafe_allow_html=True)
    st.image("https://example.com/mollier_diagram.png", caption="몰리에 선도")