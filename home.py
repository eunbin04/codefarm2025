# home.py
import streamlit as st


def show_home():
    st.title('안녕하세요! 👋')
    st.write('4조 코드팜입니다.')
    st.write('⬅️왼쪽 메뉴를 통해 대시보드 페이지로 이동하세요.')

    st.markdown("## 메뉴 바로가기")

    cols = st.columns(2)

    with cols[0]:
        if st.button("🏠 홈\n\n메인 페이지로 이동", key="card_home"):
            set_page("홈")

    with cols[1]:
        if st.button("📊 대시보드\n\n데이터 시각화", key="card_dashboard"):
            set_page("대시보드")

    with cols[0]:
        if st.button("🌿 온실 환경 관리\n\n센서 데이터 보기", key="card_greenhouse"):
            set_page("온실 환경 관리")

    with cols[1]:
        if st.button("🚨 알림\n\n경고 및 이벤트", key="card_alerts"):
            set_page("알림")
