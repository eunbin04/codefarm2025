# alarms.py
import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta


def color_status(val, correction):
    if correction != "":
        color = "lightgreen"  # 자동 보정 완료
    else:
        color = "lightcoral"  # 미완료
    return f"background-color: {color}"


def initialize_alarm_data():
    alarm_types = ["온도", "습도", "광"]
    states = ["이상치", "결측치"]
    base_time = datetime.strptime("2025-11-04 08:00", "%Y-%m-%d %H:%M")

    random.seed(42)

    alarm_data = {
        "시간": [],
        "알림 유형": [],
        "상태": [],
        "설명": [],
        "보정내역": []
    }
    for i in range(10):
        alarm_type = random.choice(alarm_types)
        state = random.choice(states)
        time = base_time + timedelta(minutes=45 * i)
        alarm_data["시간"].append(time.strftime("%Y-%m-%d %H:%M"))
        alarm_data["알림 유형"].append(alarm_type)
        alarm_data["상태"].append(state)
        alarm_data["설명"].append(f"{alarm_type} 솔루션{random.randint(1, 2)}")
        
        # 항상 아래 한 줄은 append 하도록, 조건문에서 분리
        if random.random() < 0.5:
            correction = ""
        else:
            correction = f"자동 보정 ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        alarm_data["보정내역"].append(correction)

    return pd.DataFrame(alarm_data)



def show_alarms():
    st.title("🚨 알림 기록")
    st.markdown("---")

    if "alarm_data" not in st.session_state:
        st.session_state.alarm_data = initialize_alarm_data()

    df_alarms = st.session_state.alarm_data

    # 자동 보정 대상 선정 로직은 삭제하여 새로고침 시 변경되지 않음

    correction_filter = st.selectbox(
        "자동 보정 여부 선택",
        options=["전체", "미완료", "완료"]
    )

    if correction_filter == "완료":
        filtered_df = df_alarms[df_alarms["보정내역"] != ""]
    elif correction_filter == "미완료":
        filtered_df = df_alarms[df_alarms["보정내역"] == ""]
    else:
        filtered_df = df_alarms

    filtered_df = filtered_df.copy()
    filtered_df["시간_dt"] = pd.to_datetime(filtered_df["시간"], format="%Y-%m-%d %H:%M")
    filtered_df = filtered_df.sort_values(by="시간_dt", ascending=False)
    filtered_df = filtered_df.drop(columns=["시간_dt"])

    styled_df = filtered_df.style.apply(
        lambda row: [color_status(row["상태"], row["보정내역"]) if col == "상태" else "" for col in filtered_df.columns],
        axis=1
    )

    st.dataframe(styled_df)

    st.subheader("알림 상세")

    alert_times = filtered_df["시간"].tolist()
    selected_alert_time = st.selectbox("항목 선택", options=alert_times)

    if selected_alert_time:
        selected_index = df_alarms[df_alarms["시간"] == selected_alert_time].index[0]
        selected_row = df_alarms.loc[selected_index]

        border_color = "#66C87F" if selected_row["보정내역"] != "" else "lightcoral"

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
            <b>보정내역:</b> {selected_row['보정내역']}<br>
        </div>
        """, unsafe_allow_html=True)


        if 'manual_correction_done' not in st.session_state:
            st.session_state.manual_correction_done = False

        if selected_row["보정내역"] == "":
            if st.button("보정하기"):
                st.session_state.manual_correction_done = True
                st.session_state.alarm_data.at[selected_index, "보정내역"] = f"수동 보정 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"

        if st.session_state.manual_correction_done:
            st.success("보정이 완료되어 반영되었습니다.")
            # 상태 변경으로 강제 UI 재실행 유도
            st.session_state.manual_correction_done = not st.session_state.manual_correction_done

