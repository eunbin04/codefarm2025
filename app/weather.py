# weather.py
import streamlit as st
import datetime
from outlier_solution.call_api import fetch_asos_daily, STN_ID, SERVICE_KEY

def show_weather():
    st.title('⛅ 기상 정보')
    st.markdown("---")

    today = datetime.date.today()
    selected_dates = st.date_input(
        "기간 선택",
        value=(today)
    )
    if isinstance(selected_dates, tuple):
        start_date, end_date = selected_dates
    else:
        start_date = end_date = selected_dates

    if start_date > end_date:
        st.error('시작일이 종료일보다 이후일 수 없습니다.')
        return

    try:
        weather_data = fetch_asos_daily(
            stn_id=STN_ID,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
            service_key=SERVICE_KEY
        )
    except Exception as e:
        st.error(f'기상청 데이터 조회 중 오류가 발생했습니다: {e}')
        return

    if weather_data is not None and not weather_data.empty:
        st.subheader("일자료 데이터")
        st.dataframe(weather_data)
        csv = weather_data.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label=":material/download: CSV 파일",
            data=csv,
            file_name='asos_daily_data.csv',
            mime='text/csv'
        )
    else:
        st.info('해당 기간에 데이터가 없습니다.')

    st.markdown("---")
    st.markdown("데이터 출처: 기상청 ASOS 일자료 API")
