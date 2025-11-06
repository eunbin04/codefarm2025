# weather.py
import streamlit as st
from outlier_solution.call_api import fetch_asos_daily, STN_ID, START_DATE, END_DATE, SERVICE_KEY


def show_weather():
    st.title('⛅ 기상 정보')

    st.markdown("---")

    # 기상청 데이터 불러오기
    weather_data = fetch_asos_daily(
        stn_id=STN_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        service_key=SERVICE_KEY
    )

    st.subheader("일자료 데이터")
    st.dataframe(weather_data)

    st.subheader("💾 데이터 다운로드")
    csv = weather_data.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="CSV 파일로 다운로드",
        data=csv,
        file_name='asos_daily_data.csv',
        mime='text/csv'
    )
    st.markdown("---")  
    st.markdown("데이터 출처: 기상청 ASOS 일자료 API")