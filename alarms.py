import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta

def color_status(val):
    if val == "해결됨":
        color = "lightgreen"
    elif val == "미해결":
        color = "lightcoral"
    elif val == "센서 오류":
        color = "lightyellow"
    else:
        color = ""
    return f"background-color: {color}"

def show_alarms():
    st.title("🚨 알림")

    alarm_types = ["이상치", "결측치", "VPD 경고"]
    states = ["해결됨", "미해결"]
    descriptions = {
        "이상치": ["온도 100℃ 감지", "CO2 농도 이상치", "조도 센서 이상"],
        "결측치": ["습도 센서에서 몇 분동안 결측 발생", "토양수분 센서 데이터 누락"],
        "VPD 경고": ["적정 VPD 범위 초과", "VPD 급격 변화 감지"]
    }

    base_time = datetime.strptime("2025-11-04 08:00", "%Y-%m-%d %H:%M")

    if "alarm_data" not in st.session_state:
        random.seed(42)
        alarm_data = {
            "시간": [],
            "알림 유형": [],
            "상태": [],
            "설명": []
        }
        for i in range(10):
            alarm_type = random.choice(alarm_types)
            state = random.choice(states)
            description = random.choice(descriptions[alarm_type])
            time = base_time + timedelta(minutes=45 * i)
            alarm_data["시간"].append(time.strftime("%Y-%m-%d %H:%M"))
            alarm_data["알림 유형"].append(alarm_type)
            alarm_data["상태"].append(state)
            alarm_data["설명"].append(description)
        st.session_state.alarm_data = pd.DataFrame(alarm_data)

    df_alarms = st.session_state.alarm_data

    status_filter = st.selectbox("알림 상태 선택", options=["전체", "해결됨", "미해결", "센서 오류"])

    if status_filter != "전체":
        filtered_df = df_alarms[df_alarms["상태"] == status_filter]
    else:
        filtered_df = df_alarms

    st.dataframe(filtered_df.style.map(color_status, subset=["상태"]))

    st.markdown("### 알림 상세")

    alert_times = filtered_df["시간"].tolist()
    selected_alert_time = st.selectbox("알림 시간 선택", options=alert_times)

    if selected_alert_time:
        selected_index = df_alarms[df_alarms["시간"] == selected_alert_time].index[0]
        selected_row = df_alarms.loc[selected_index]

        border_color = "#4CAF50" if selected_row["상태"] == "해결됨" else ("#FFEB3B" if selected_row["상태"] == "센서 오류" else "#FF6347")

        st.markdown(f"""
        <div style="
            border: 2px solid {border_color};
            padding: 15px;
            border-radius: 10px;
            background-color: #f9f9f9;
            margin-bottom: 20px;
        ">
            <h3>{selected_row['알림 유형']}</h3>
            <b>시간:</b> {selected_row['시간']}<br>
            <b>상태:</b> {selected_row['상태']}<br>
            <b>설명:</b> {selected_row['설명']}<br>
            <ul>
                {"<li>센서 점검 필요</li><li>시스템 로그 확인</li>" if selected_row["상태"] == "미해결" else "<li>이미 해결된 알림입니다.</li>"}
            </ul>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        if selected_row["상태"] == "미해결":
            with col1:
                if st.button("센서 오류로 변경", key="sensor_error"):
                    st.session_state.alarm_data.at[selected_index, "상태"] = "센서 오류"
            with col2:
                if st.button("해결 완료", key="resolved"):
                    st.session_state.alarm_data.at[selected_index, "상태"] = "해결됨"
