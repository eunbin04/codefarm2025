# streamlit_app.py
import streamlit as st
from home import show_home
from dashboard import show_vpd, show_period
from sensordata import show_mcdata, show_mediadata
from alarms import show_alarms
from settings import show_settings


st.set_page_config(page_title='CODEFARM', page_icon=':seedling:')

st.sidebar.title('메뉴')


if st.sidebar.button('🏠 홈'):
    st.write("홈 페이지 표시")

with st.sidebar.expander('📈 대시보드'):
    if st.button('VPD 관련'):
        st.write("대시보드 - VPD 관련")
    if st.button('기간별 데이터'):
        st.write("대시보드 - 기간별 데이터")

with st.sidebar.expander('🌿 모니터링'):
    if st.button('미기후 정보'):
        st.write("모니터링 - 미기후 정보")
    if st.button('배지 정보'):
        st.write("모니터링 - 배지 정보")

if st.sidebar.button('🚨 알림'):
    st.write("알림 페이지")

if st.sidebar.button('⚙️ 설정'):
    st.write("설정 페이지")



st.sidebar.markdown("---")
st.sidebar.markdown("© 2025 CODEFARM")
st.sidebar.markdown("<strong>개발자<strong/>", unsafe_allow_html=True)
st.sidebar.markdown("김유경<br>박은빈<br>박주영<br>신예은<br>우가연", unsafe_allow_html=True)