import streamlit as st

def show_home():
    st.title('안녕하세요! 👋')
    st.write('4조 코드팜입니다.')
    st.write('⬅️왼쪽 메뉴를 통해 대시보드 페이지로 이동하세요.')


st.markdown("---")  # 구분선 추가


col1, col2 = st.columns(2)

with col1:
    st.header("온도 및 습도")
    # 온도, 습도 관련 시각화

with col2:
    st.header("CO2 및 조도")
    # CO2, 조도 관련 시각화

st.markdown("---")  # 구분선 추가

with st.container():
    st.subheader("온도 데이터")
    # 온도 관련 차트, 텍스트 등 넣기

st.markdown("---")  # 구분선 추가

with st.container():
    st.subheader("습도 데이터")
    # 습도 관련 내용

with st.expander("온도 상세 보기"):
    st.line_chart(temperature_data)

with st.expander("습도 상세 보기"):
    st.line_chart(humidity_data)


st.markdown('<div class="stCard">내용</div>', unsafe_allow_html=True)
