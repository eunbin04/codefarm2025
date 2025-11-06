import streamlit as st
import math

def calc_vpd(temp_c, rh):
    svp = 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    vpd = svp * (1 - rh / 100)
    return round(vpd, 3)

def show_dashboard():
    st.title("📈 대시보드")

    st.markdown("### VPD 계산기")

    temp = st.number_input("🔥 온도 (°C)", min_value=-10.0, max_value=40.0, value=25.0, step=1.0)
    rh = st.number_input("💧 상대습도 (%)", min_value=0.0, max_value=100.0, value=70.0, step=1.0)

    vpd = calc_vpd(temp, rh)
    st.metric(label="VPD", value=f"{vpd:.2f} kPa")

    if 0.8 <= vpd <= 1.2:
        st.success("이상적인 VPD 범위(생육 촉진 구간)입니다.")
    elif 1.2 < vpd <= 1.5:
        st.warning("개화단계에 적합한 VPD 범위입니다.")
    else:
        st.error("비이상적 VPD입니다. 환경 조정 필요!")

    st.markdown("""
    <details>
    <summary><b>식물의 생장 단계별 VPD 최적 구간</b></summary><br
    클론, 뿌리 형성 단계: 0.8 kPa<br>
    영양 생장: VPD 1.0 kPa<br>
    생식생장: VPD 1.2~1.5 kPa

    </details>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    show_dashboard()
