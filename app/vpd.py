# vpd.py
import streamlit as st
import math
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def calc_vpd(temp_c, rh):
    svp = 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    vpd = svp * (1 - rh / 100)
    return round(vpd, 3)


def show_vpd():
    st.title("🧮 VPD 계산기")

    st.markdown("---")

    # 수정된 number_input
    col1, col2 = st.columns(2)
    with col1:
        temp = st.number_input("🌡️ 온도 (°C)", min_value=-20.0, max_value=60.0, value=25.0, step=1.0, format="%.1f")
    with col2:
        rh = st.number_input("💧 상대습도 (%)", min_value=0.0, max_value=100.0, value=70.0, step=1.0, format="%.1f")
    vpd = calc_vpd(temp, rh)
    st.metric(label="VPD", value=f"{vpd:.2f} kPa")

    if 0.8 <= vpd <= 1.2:
        st.success("이상적인 VPD 범위(생육 촉진 구간)입니다.")
    elif 1.2 < vpd <= 1.5:
        st.warning("개화단계에 적합한 VPD 범위입니다.")
    else:
        st.error("비이상적 VPD입니다. 환경 조정 필요")

    temps = np.linspace(-20, 60, 100)
    rhs = np.linspace(0, 100, 100)
    T, RH = np.meshgrid(temps, rhs)
    VPD = 0.6108 * np.exp((17.27 * T) / (T + 237.3)) * (1 - RH / 100)

    fig, ax = plt.subplots(figsize=(8, 6))

    levels = [0, 0.8, 1.5, np.max(VPD) + 0.1]
    colors = ["#5e8fce7f", "#92de9f8f", "#e8807b89"]

    c = ax.contourf(T, RH, VPD, levels=levels, colors=colors, alpha=0.7)
    contours = ax.contour(T, RH, VPD, levels=levels, colors='black', linewidths=0.7)

    cbar = fig.colorbar(c, ax=ax, boundaries=levels)
    cbar.set_ticks([0.4, 1.15, 7.5])
    cbar.set_ticklabels(['low', 'Optimal', 'high'])

    ax.set_xlabel('temperature (°C)')
    ax.set_ylabel('humidity (%)')

    # 그리드 색과 스타일 변경
    ax.grid(color='gray', linestyle='--', linewidth=0.8)

    ax.xaxis.set_major_locator(mticker.MultipleLocator(5))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))

    # 선택값을 축과 이어주는 붉은색 선 그리기
    ax.axvline(x=temp, color='red', linestyle='-', linewidth=2, alpha=0.7)
    ax.axhline(y=rh, color='red', linestyle='-', linewidth=2, alpha=0.7)

    # 현재 위치 붉은 점으로 표시
    ax.scatter(temp, rh, color='red', s=100, label=f'VPD: {vpd:.2f} kPa')
    ax.legend()

    st.pyplot(fig)
    plt.clf()

    st.markdown("""
    <details>
    <summary><b>작물의 생장 단계별 VPD 최적 구간</b></summary>
    - 클론, 뿌리 형성 단계: 0.8 kPa<br>
    - 영양 생장: VPD 1.0 kPa<br>
    - 생식생장: VPD 1.2~1.5 kPa
    </details>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    show_vpd()
