# streamlit_app.py
import streamlit as st
from home import show_home
from dashboard import show_vpd, show_period
from sensordata import show_mcdata, show_mediadata
from alarms import show_alarms
from settings import show_settings


st.set_page_config(page_title='CODEFARM', page_icon=':seedling:')

st.sidebar.title('메뉴')

main_page = st.sidebar.radio('', ['🏠홈', '📈대시보드', '🌿모니터링', '🚨알림', '⚙️설정'])

def sidebar_footer():
    st.sidebar.markdown("---")
    st.sidebar.markdown("© 2025 CODEFARM")
    st.sidebar.markdown("<strong>개발자<strong/>", unsafe_allow_html=True)
    st.sidebar.markdown("김유경<br>박은빈<br>박주영<br>신예은<br>우가연", unsafe_allow_html=True)


main_page = st.sidebar.selectbox(
    '메뉴 선택',
    ['🏠홈', '📈대시보드', '🌿모니터링', '🚨알림', '⚙️설정']
)

if main_page == '📈대시보드':
    dashboard_sub = st.sidebar.selectbox(
        '대시보드 세부 메뉴',
        ['기간별 데이터', 'VPD 데이터']
    )
    if dashboard_sub == 'VPD 데이터':
        show_vpd()
    else:
        show_period()
elif main_page == '🌿모니터링':
    monitoring_sub = st.sidebar.selectbox(
        '모니터링 세부 메뉴',
        ['미기후 정보', '배지 정보']
    )
    if monitoring_sub == '미기후 정보':
        show_mcdata()
    else:
        show_mediadata()
elif main_page == '🏠홈':
    show_home()
elif main_page == '🚨알림':
    show_alarms()
elif main_page == '⚙️설정':
    show_settings()


sidebar_footer()