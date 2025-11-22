# settings.py
import streamlit as st
import json
import os
from utils import get_korea_time

SETTINGS_FILE = "config/settings.json"

def save_settings_to_file():
    settings_data = {
        "farm_name": st.session_state.get('farm_name', "CODEFARM 온실"),
        "alert_enabled": st.session_state.get('alert_enabled', True),
        "daily_stat_time": st.session_state.get('daily_stat_time', "09:00"),
        "auto_train_time": st.session_state.get('auto_train_time', "02:00"),
        "t_location": st.session_state.get('t_location', 1),
        "h_location": st.session_state.get('h_location', 3),
        "r_location": st.session_state.get('r_location', 4),
    }
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings_data, f, ensure_ascii=False, indent=4)

def load_settings_from_file():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        for key, val in settings.items():
            st.session_state[key] = val
    else:
        if 'farm_name' not in st.session_state:
            st.session_state['farm_name'] = "CODEFARM 온실"
        if 'alert_enabled' not in st.session_state:
            st.session_state['alert_enabled'] = True
        if 'daily_stat_time' not in st.session_state:
            st.session_state['daily_stat_time'] = "09:00"
        if 'auto_train_time' not in st.session_state:
            st.session_state['auto_train_time'] = "02:00"
        if 't_location' not in st.session_state:
            st.session_state['t_location'] = 1
        if 'h_location' not in st.session_state:
            st.session_state['h_location'] = 3
        if 'r_location' not in st.session_state:
            st.session_state['r_location'] = 4

def show_settings():
    st.title("⚙️ 설정")
    st.markdown("---")

    if st.session_state.get("loaded", False) is False:
        load_settings_from_file()
        st.session_state["loaded"] = True

    korea_now = get_korea_time()

    with st.form("settings_form"):
        st.markdown("##### 기본 설정")
        farm_name = st.text_input("농장명", value=st.session_state['farm_name'])

        alert_options = {True: "🔔 활성화", False: "🔕 비활성화"}
        alert_enabled = st.selectbox(
            "경고 알림 설정",
            options=[True, False],
            format_func=lambda x: alert_options[x],
            index=0 if st.session_state['alert_enabled'] else 1,
            help="데이터에 이상이 있을 때 알림을 받습니다."
        )

        st.markdown("---")
        st.markdown("##### 🕒 하루 통계 수신 시각 설정")
        hours = [f"{i:02d}" for i in range(24)]
        minutes = [f"{i:02d}" for i in range(60)]
        # 데이터 수신 시각
        if 'daily_stat_time' in st.session_state:
            h, m = st.session_state['daily_stat_time'].split(':')
        else:
            h = f"{korea_now.hour:02d}"
            m = f"{korea_now.minute:02d}"

        col1, col2 = st.columns([1, 1])
        with col1:
            selected_hour = st.selectbox("시", options=hours, index=hours.index(h))
        with col2:
            selected_minute = st.selectbox("분", options=minutes, index=minutes.index(m),
                                           help="24시간 동안의 데이터 통계량을 분석해 알립니다.")
        daily_stat_time = f"{selected_hour}:{selected_minute}"

        st.markdown("---")
        st.markdown("##### ⌛ 자동 모델 학습 시각 설정")
        if 'auto_train_time' in st.session_state:
            ath, atm = st.session_state['auto_train_time'].split(':')
        else:
            ath = "02"
            atm = "00"
        c1, c2 = st.columns([1, 1])
        with c1:
            auto_train_hour = st.selectbox("시", options=hours, index=hours.index(ath), key="auto_train_hour")
        with c2:
            auto_train_minute = st.selectbox("분", options=minutes, index=minutes.index(atm), key="auto_train_minute", 
                                             help="데이터 학습 모델의 학습 주기를 설정합니다.")
        auto_train_time = f"{auto_train_hour}:{auto_train_minute}"

        st.markdown("---")
        st.markdown("##### 🎯 데이터 인덱스 설정")
        st.markdown("컬럼 인덱스는 **0부터 시작**합니다. CSV/엑셀 파일 열 번호를 참고하세요.")
        t_location = st.number_input("온도 인덱스", min_value=0, value=st.session_state.get('t_location', 1))
        h_location = st.number_input("습도 인덱스", min_value=0, value=st.session_state.get('h_location', 3))
        r_location = st.number_input("광 인덱스", min_value=0, value=st.session_state.get('r_location', 4))

        submitted = st.form_submit_button("저장")

        if submitted:
            st.session_state['farm_name'] = farm_name
            st.session_state['alert_enabled'] = alert_enabled
            st.session_state['daily_stat_time'] = daily_stat_time
            st.session_state['auto_train_time'] = auto_train_time
            st.session_state['t_location'] = int(t_location)
            st.session_state['h_location'] = int(h_location)
            st.session_state['r_location'] = int(r_location)
            save_settings_to_file()
            st.success("설정이 저장되었습니다!")