# alarms.py
import streamlit as st
import pandas as pd

def color_status(val):
    if val == "해결됨":
        color = "lightgreen"
    elif val == "미해결":
        color = "lightcoral"
    else:
        color = ""
    return f"background-color: {color}"


def show_alarms():
    st.title("🚨 알림")

    alarm_data = {
        "시간": ["2025-11-04 08:15", "2025-11-04 09:30", "2025-11-04 10:45"],
        "알림 유형": ["이상치", "결측치", "VPD 경고"],
        "상태": ["해결됨", "미해결", "해결됨"],
        "설명": [
            "온도 100℃ 감지",
            "습도 센서에서 몇 분동안 결측 발생",
            "적정 VPD 범위 초과"
        ]
    }

    df_alarms = pd.DataFrame(alarm_data)

    status_filter = st.selectbox("알림 상태 선택", options=["전체", "해결됨", "미해결"])

    if status_filter == "전체":
        filtered_df = df_alarms
    else:
        filtered_df = df_alarms[df_alarms["상태"] == status_filter]

    st.dataframe(filtered_df.style.applymap(color_status, subset=["상태"]))

    st.markdown("### 알림 상세")


    # 알림 유형을 선택지로 사용
    alert_types = filtered_df["알림 유형"].tolist()
    selected_alert_type = st.selectbox("상세보기 알림 유형 선택", options=alert_types)

    if selected_alert_type:
        selected_row = filtered_df[filtered_df["알림 유형"] == selected_alert_type].iloc[0]

        box_style = """
        <div style="
            border: 2px solid #4CAF50;  /* 초록색 테두리 */
            padding: 15px;
            border-radius: 10px;
            background-color: #f9f9f9;
            margin-bottom: 20px;
            ">
        """

        box_end = "</div>"

        st.markdown(box_style, unsafe_allow_html=True)
        st.markdown(f"### {selected_row['알림 유형']}")
        st.markdown(f"**시간:** {selected_row['시간']}")
        st.markdown(f"**상태:** {selected_row['상태']}")
        st.markdown(f"**설명:** {selected_row['설명']}")
        st.markdown(box_end, unsafe_allow_html=True)

        st.markdown("#### 조치 방법")
        if selected_row["상태"] == "미해결":
            st.write("- 센서 점검 필요")
            st.write("- 시스템 로그 확인")
        else:
            st.write("- 이미 해결된 알림입니다.")
        st.markdown("---")

        
