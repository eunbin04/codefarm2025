import streamlit as st
from home import show_home
from dashboard import show_dashboard
from alarms import show_alarms
from sensordata import show_sensordata

st.set_page_config(page_title='CODEFARM', page_icon=':seedling:')

st.sidebar.title('🔍 메뉴')
page = st.sidebar.radio('페이지 선택', ['홈', '온실 환경 관리', 'Alarms', 'Sensor Data'])

if page == '홈':
    show_home()
elif page == '온실 환경 관리':
    show_dashboard()
elif page == 'Alarms':
    show_alarms()
elif page == 'Sensor Data':
    show_sensordata()


st.sidebar.markdown("---")  
st.sidebar.markdown("© 2025 CODEFARM")
