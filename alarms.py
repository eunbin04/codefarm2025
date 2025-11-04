import streamlit as st
import pandas as pd

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

    st.dataframe(df_alarms.style.applymap(color_status, subset=["상태"]))

    st.markdown("#### 알림 상세")
    selected = st.selectbox("알림 선택", df_alarms.index)
    if selected is not None:
        st.write("###", df_alarms.loc[selected, "알림 유형"])
        st.write("시간:", df_alarms.loc[selected, "시간"])
        st.write("상태:", df_alarms.loc[selected, "상태"])
        st.write("설명:", df_alarms.loc[selected, "설명"])


def color_status(val):
    if val == "해결됨":
        color = "lightgreen"
    elif val == "미해결":
        color = "lightcoral"
    else:
        color = ""
    return f"background-color: {color}"
