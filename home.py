# home.py
import streamlit as st


def show_home():
    st.title('안녕하세요! 👋')
    st.write('4조 코드팜입니다.')
    st.write('⬅️왼쪽 메뉴를 통해 대시보드 페이지로 이동하세요.')

    st.markdown("## 메뉴 바로가기")

    cols = st.columns(2)

    with cols[0]:
        if st.button("🏠 홈"):
            st.experimental_set_query_params(page="홈")
    with cols[1]:
        if st.button("📊 대시보드"):
            st.experimental_set_query_params(page="대시보드")

    with cols[0]:
        if st.button("🌿 온실 환경 관리"):
            st.experimental_set_query_params(page="온실 환경 관리")
    with cols[1]:
        if st.button("🚨 알림"):
            st.experimental_set_query_params(page="알림")

    # 방법 2: 버튼 대신 클릭 가능한 카드 형태(이미지+텍스트) 등으로 꾸밀 수도 있음.
