import streamlit as st
from home import show_home
from dashboard import show_dashboard

st.sidebar.title('네비게이션')
page = st.sidebar.radio('페이지 선택', ['홈', '환경 대시보드'])

if page == '홈':
    show_home()
elif page == '환경 대시보드':
    show_dashboard()

# 사이드바 타이틀
st.sidebar.title("🔍 메뉴")

# 네비게이션 선택지 리스트
menu = ["🏠 홈", "🌿 환경 대시보드", "📊 통계"]

# 라디오 버튼 스타일에 맞게 메뉴 선택
choice = st.sidebar.radio("페이지 선택", menu)

# 네비게이션 아이콘과 이름에 따라 페이지 구분
if choice == "🏠 홈":
    st.write("# 홈 페이지")
    st.write("이곳은 홈 화면입니다.")
elif choice == "🌿 환경 대시보드":
    st.write("# 환경 대시보드")
    st.write("실시간 환경 데이터를 확인하세요.")

    st.sidebar.markdown("## 🔖 내비게이션")

menu = ["🏠 홈", "🌿 환경 대시보드"]
choice = st.sidebar.radio("메뉴 선택", menu)

st.sidebar.markdown("---")  # 구분선
st.sidebar.markdown("© 2025 CODEFARM")
