# app.py
import streamlit as st
from home import show_home
from streamlit_app import show_dashboard

st.set_page_config(page_title='CODEFARM', page_icon=':seedling:')

st.sidebar.title('네비게이션')
page = st.sidebar.radio('페이지 선택', ['홈', '환경 대시보드'])

if page == '홈':
    show_home()
elif page == '환경 대시보드':
    show_dashboard()
