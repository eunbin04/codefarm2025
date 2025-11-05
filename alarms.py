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

    # 예시 알림 데이터 (시간, 알림 유형, 상태, 설명)
    alarm_data = {
        "시간": ["2025-11-04 08:15", "2025-11-04 09:30", "2025-11-04 10:45"],
        "알림 유형": ["온도 초과", "습도 부족", "CO2 이상"],
        "상태": ["해결됨", "미해결", "해결됨"],
        "설명": [
            "온도가 35도 이상 감지되어 경고 발생",
            "습도 30% 이하로 떨어져 경고 발생",
            "CO2 농도가 기준치를 초과함"
        ]
    }

    df_alarms = pd.DataFrame(alarm_data)

    # 상태별 필터링 셀렉트박스
    status_filter = st.selectbox("알림 상태 선택", options=["전체", "해결됨", "미해결"])

    if status_filter == "전체":
        filtered_df = df_alarms
    else:
        filtered_df = df_alarms[df_alarms["상태"] == status_filter]

    st.dataframe(filtered_df.style.applymap(color_status, subset=["상태"]))

    st.markdown("### 알림 상세")
    selected = st.selectbox("알림 선택", filtered_df.index)
    if selected is not None:
        st.write("###", filtered_df.loc[selected, "알림 유형"])
        st.write("시간:", filtered_df.loc[selected, "시간"])
        st.write("상태:", filtered_df.loc[selected, "상태"])
        st.write("설명:", filtered_df.loc[selected, "설명"])
        if filtered_df.loc[selected, "상태"] == "미해결":
            if st.button("해결됨으로 표시"):
                filtered_df.at[selected, "상태"] = "해결됨"
                st.success("알림 상태가 '해결됨'으로 업데이트되었습니다.")  