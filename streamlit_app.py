# streamlit_app.py
import streamlit as st
from app.home import show_home
from app.setdb import show_setdb
from app.cleandata import show_cleandata
from app.vpd import show_vpd
from app.weather import show_weather
from app.perdata import show_perdata
from app.rtdata import show_rtdata
from app.alarms import show_alarms
from app.settings import show_settings
from auth import authenticate, load_users
import time

# 로그인 세션 관리
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user" not in st.session_state:
    st.session_state.user = None

users_df = load_users()

def login_page():
    st.title("LOGIN")
    username = st.text_input("아이디")
    password = st.text_input("비밀번호", type="password")

    if st.button("로그인"):
        user = authenticate(username, password, users_df)
        if user:
            st.session_state.logged_in = True
            st.session_state.user = user
            st.success(f"환영합니다! {user['name']} 님 😊")
            with st.spinner("로그인 중..."):
                time.sleep(3)
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 잘못되었습니다")

def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()


st.set_page_config(page_title='CODEFARM', page_icon=':seedling:', layout='wide')

if st.session_state.logged_in:
    st.sidebar.markdown(f"**👤 {st.session_state.user['name']}님**")
    if st.sidebar.button("🔓 로그아웃"):
        logout()

st.sidebar.markdown("---")
st.sidebar.title('Menu')

if 'page' not in st.session_state:
    st.session_state.page = '홈'  

def set_page(page_name):
    st.session_state.page = page_name

# 스타일용 버튼 크기 맞춤 (CSS 삽입)
button_style = """
    <style>
    div.stButton > button {
        width: 100%;
        height: 2.7em;
        font-size: 1rem;
        text-align: left;
    }
    </style>
    """
st.sidebar.markdown(button_style, unsafe_allow_html=True)

# 로그인 체크
if not st.session_state.logged_in:
    login_page()
    st.stop()

if st.sidebar.button('🏠 홈'):
    set_page('홈')

with st.sidebar.expander("🗃️ 데이터 관리", expanded=True):
    if st.button('DB 관리'):
        set_page('DB 관리')
    if st.button('데이터 보정'):
        set_page('데이터 보정')
    if st.button('기간별 데이터'):
        set_page('기간별 데이터')


with st.sidebar.expander("📈 모니터링", expanded=True):
    if st.button('기상 정보'):
        set_page('기상 정보')
    if st.button('알림 기록'):
        set_page('알림 기록')
    if st.button('실시간 데이터'):
        set_page('실시간 데이터')

if st.sidebar.button('🧮 VPD 계산기'):
    set_page('VPD 계산기')

if st.sidebar.button('⚙️ 설정'):
    set_page('설정')

# 페이지별 화면 표시
if st.session_state.page == '홈':
    show_home()
elif st.session_state.page == 'DB 관리':
    show_setdb()
elif st.session_state.page == '데이터 보정':
    show_cleandata()
elif st.session_state.page == '기간별 데이터':
    show_perdata()
elif st.session_state.page == '기상 정보':
    show_weather()
elif st.session_state.page == '알림 기록':
    show_alarms()
elif st.session_state.page == '실시간 데이터':
    show_rtdata()
elif st.session_state.page == 'VPD 계산기':
    show_vpd()
elif st.session_state.page == '설정':
    show_settings()


st.sidebar.markdown("---")
st.sidebar.markdown("<strong>개발자<strong/>", unsafe_allow_html=True)
st.sidebar.markdown("김유경<br>박은빈<br>박주영<br>신예은<br>우가연", unsafe_allow_html=True)
st.sidebar.markdown("© 2025 CODEFARM")