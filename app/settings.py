# settings.py
import streamlit as st
import json
import os

SETTINGS_FILE = "config/settings.json"

def save_settings_to_file():
    # 세션 상태의 설정값을 JSON 파일로 저장
    settings_data = {
        "farm_name": st.session_state.get('farm_name', "CODEFARM 온실"),
        "alert_enabled": st.session_state.get('alert_enabled', True),
        "update_interval": st.session_state.get('update_interval', 30),
        "h_location": st.session_state.get('h_location', 3),
        "r_location": st.session_state.get('r_location', 4),
        "t_location": st.session_state.get('t_location', 1),
    }
    # config 폴더가 없으면 생성
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings_data, f, ensure_ascii=False, indent=4)

def load_settings_from_file():
    # 앱 시작 시 JSON파일이 있으면 불러와 세션 상태 초기화
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        for key, val in settings.items():
            st.session_state[key] = val
    else:
        # 기본값 세팅
        if 'farm_name' not in st.session_state:
            st.session_state['farm_name'] = "CODEFARM 온실"
        if 'alert_enabled' not in st.session_state:
            st.session_state['alert_enabled'] = True
        if 'update_interval' not in st.session_state:
            st.session_state['update_interval'] = 30
        if 'h_location' not in st.session_state:
            st.session_state['h_location'] = 3
        if 'r_location' not in st.session_state:
            st.session_state['r_location'] = 4
        if 't_location' not in st.session_state:
            st.session_state['t_location'] = 1

def show_settings():
    st.title("⚙️ 설정")
    st.markdown("---")

    # 앱 시작 시 설정파일 존재하면 세션 상태에 로드
    if st.session_state.get("loaded", False) is False:
        load_settings_from_file()
        st.session_state["loaded"] = True

    with st.form("settings_form"):
        farm_name = st.text_input("농장명", value=st.session_state['farm_name'])
        alert_enabled = st.checkbox("경고 알림 활성화", value=st.session_state['alert_enabled'])
        update_interval = st.slider("데이터 업데이트 주기 (분)", min_value=5, max_value=120,
                                    value=st.session_state['update_interval'], step=5)

        st.markdown("- 인덱스는 0부터 시작")
        h_location = st.number_input("습도 인덱스", min_value=0,
                                     value=st.session_state['h_location'])
        r_location = st.number_input("광 인덱스", min_value=0,
                                     value=st.session_state['r_location'])
        t_location = st.number_input("온도 인덱스", min_value=0,
                                     value=st.session_state['t_location'])

        submitted = st.form_submit_button("저장")

        if submitted:
            st.session_state['farm_name'] = farm_name
            st.session_state['alert_enabled'] = alert_enabled
            st.session_state['update_interval'] = update_interval
            st.session_state['h_location'] = int(h_location)
            st.session_state['r_location'] = int(r_location)
            st.session_state['t_location'] = int(t_location)
            save_settings_to_file()
            st.success("설정이 세션과 파일에 저장되었습니다!")

    st.subheader("현재 설정")
    st.write(f"농장명: {st.session_state['farm_name']}")
    st.write(f"경고 알림 활성화: {'✔️' if st.session_state['alert_enabled'] else '❌'}")
    st.write(f"데이터 업데이트 주기: {st.session_state['update_interval']} 분")
    st.write(f"습도 인덱스: {st.session_state['h_location']}")
    st.write(f"광 인덱스: {st.session_state['r_location']}")
    st.write(f"온도 인덱스: {st.session_state['t_location']}")