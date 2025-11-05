# dashboard.py
import streamlit as st
import math
import requests

def calc_vpd(temp_c, rh):
    svp = 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    vpd = svp * (1 - rh / 100)
    return round(vpd, 3)

def show_dashboard():
    st.title("📈 대시보드")

    # 지역 입력 및 날씨 불러오기
    region = st.text_input("지역명을 입력하세요", "서울")
    if st.button("날씨 불러오기"):
        # 예시용 가상 값 및 API 호출 구간
        temp = 25  # 실시간 API로 가져올 값
        rh = 70    # 실시간 API로 가져올 값
        st.success(f"현재 온도: {temp}°C, 상대습도: {rh}%")
    else:
        temp = 25
        rh = 70

    # VPD 계산
    vpd = calc_vpd(temp, rh)
    st.metric(label="VPD 증기압 결핍", value=f"{vpd} kPa")

    # 이상적 범위 판별, 몰리에 선도 기준 메시지
    if 0.8 <= vpd <= 1.2:
        st.success("이상적인 VPD 범위(생육 촉진 구간)입니다.")
    elif 1.2 < vpd <= 1.5:
        st.warning("개화단계에 적합한 VPD 범위입니다.")
    else:
        st.error("비이상적 VPD입니다. 환경 조정 필요!")

    st.markdown("""
    <details>
    <summary><b>몰리에 선도 설명</b></summary>
    식물의 생장 최적 구간: VPD 0.8~1.2 kPa<br>
    개화단계 적합: VPD 1.2~1.5 kPa<br>
    광합성 최적: VPD 0.45~1.136 kPa
    </details>
    """, unsafe_allow_html=True)
