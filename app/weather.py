# weather.py
import streamlit as st
import datetime
from outlier_solution.call_api import fetch_asos_daily, STN_ID, SERVICE_KEY


def show_weather():
    st.title('⛅ 기상 정보')
    st.markdown("---")
    
    # 오늘 날짜 구하기
    today = datetime.date.today()
    one_month_ago = today - datetime.timedelta(days=30)
    
    # 날짜 선택 위젯 (범위 선택)
    start_date, end_date = st.date_input(
        "조회할 날짜 범위 선택", 
        value=(one_month_ago, today),
        min_value=datetime.date(2000, 1, 1),   # 필요에 따라 조정
        max_value=today
    )
    
    # 기상청 API 호출
    if start_date > end_date:
        st.error('시작일이 종료일보다 이후일 수 없습니다.')
    else:
        weather_data = fetch_asos_daily(
            stn_id=STN_ID,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
            service_key=SERVICE_KEY
        )
        st.subheader("일자료 데이터")
        st.dataframe(weather_data)
        
        csv = weather_data.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="💾 CSV 파일",
            data=csv,
            file_name='asos_daily_data.csv',
            mime='text/csv'
        )
        st.markdown("---")
        st.markdown("데이터 출처: 기상청 ASOS 일자료 API")
