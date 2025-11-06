# settings.py
import streamlit as st
import pandas as pd

def show_settings():
    st.title("⚙️ 설정")

    st.markdown("---")  

    # 기본값 설정 (세션 상태에 없으면 초기값 부여)
    if 'farm_name' not in st.session_state:
        st.session_state['farm_name'] = "CODEFARM 온실"
    if 'alert_enabled' not in st.session_state:
        st.session_state['alert_enabled'] = True
    if 'update_interval' not in st.session_state:
        st.session_state['update_interval'] = 30  # 분 단위

    with st.form("settings_form"):
        farm_name = st.text_input("농장명", value=st.session_state['farm_name'])
        alert_enabled = st.checkbox("경고 알림 활성화", value=st.session_state['alert_enabled'])
        update_interval = st.slider("데이터 업데이트 주기 (분)", min_value=5, max_value=120, value=st.session_state['update_interval'], step=5)

        submitted = st.form_submit_button("저장")

        if submitted:
            st.session_state['farm_name'] = farm_name
            st.session_state['alert_enabled'] = alert_enabled
            st.session_state['update_interval'] = update_interval
            st.success("설정이 저장되었습니다!")


    st.subheader("현재 설정")

    st.write(f"농장명: {st.session_state['farm_name']}")
    st.write(f"경고 알림 활성화: {'✔️' if st.session_state['alert_enabled'] else '❌'}")
    st.write(f"데이터 업데이트 주기: {st.session_state['update_interval']} 분")