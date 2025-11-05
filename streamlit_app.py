import streamlit as st
from home import show_home
from dashboard import show_dashboard
from alarms import show_alarms
from sensordata import show_sensordata
from settings import show_settings

st.set_page_config(page_title='CODEFARM', page_icon=':seedling:')

st.sidebar.title('🔍 메뉴')
page = st.sidebar.radio('페이지 선택', ['홈', '대시보드', '온실 환경 관리', '알림', '설정'])

if page == '홈':
    show_home()
elif page == '대시보드':
    show_dashboard()
elif page == '온실 환경 관리':
    show_sensordata()
elif page == '알림':
    show_alarms()
elif page == '설정':
    show_settings() 
    


st.sidebar.markdown("---")  
st.sidebar.markdown("© 2025 CODEFARM")
st.sidebar.markdown("<strong>개발자<strong/>", unsafe_allow_html=True)
st.sidebar.markdown("- 김유경")
st.sidebar.markdown("- 박은빈")
st.sidebar.markdown("- 박주영")
st.sidebar.markdown("- 신예은")
st.sidebar.markdown("- 우가연")