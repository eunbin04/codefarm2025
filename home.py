import streamlit as st

def show_home():
    st.title('안녕하세요! 👋')
    st.write('4조 코드팜입니다.')
    st.write('⬅️왼쪽 메뉴를 통해 대시보드 페이지로 이동하세요.')

    st.markdown("## 메뉴 바로가기")

    cols = st.columns(2)

    with cols[0]:
        if st.button("🏠 홈", key="home_btn"):
            st.experimental_set_query_params(page="홈")
        st.markdown(
            """
            <style>
            button[key="home_btn"] {
                background-color: #fff9c4 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    with cols[1]:
        if st.button("📊 대시보드", key="dashboard_btn"):
            st.experimental_set_query_params(page="대시보드")

    with cols[0]:
        if st.button("🌿 온실 환경 관리", key="greenhouse_btn"):
            st.experimental_set_query_params(page="온실 환경 관리")

    with cols[1]:
        if st.button("🚨 알림", key="alert_btn"):
            st.experimental_set_query_params(page="알림")
    
    st.markdown("""
        <style>
        button[key="dashboard_btn"] {
            background-color: #bbdefb !important;
        }
        button[key="greenhouse_btn"] {
            background-color: #c8e6c9 !important;
        }
        button[key="alert_btn"] {
            background-color: #ffcdd2 !important;
        }
        </style>
        """, unsafe_allow_html=True)
