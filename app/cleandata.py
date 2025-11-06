# cleandata.py
import streamlit as st
import datetime as datetime
from outlier_fix.train_models import train_models

def show_cleandata():
    st.title("📈 대시보드")

    st.markdown("### 모델 학습 이력 보기")

    # 실행 버튼 만들기
    if st.button("모델 학습 실행"):
        with st.spinner("모델 학습 중... 잠시만 기다려주세요"):
            result = train_models()
        st.success("모델 학습이 완료되었습니다!")
        # 학습 로그 파일 저장
        with open("outlier_fix/train_log.txt", "w") as f:
            f.write(f"{datetime.datetime.now()}\n") 

    # 파일에 쌓인 학습 로그
    try:
        with open("outlier_fix/train_log.txt", "r") as f:
            log_content = f.read()
        st.markdown("### 이전 학습 실행 로그")
        st.text(log_content)
    except FileNotFoundError:
        st.info("아직 실행 로그가 없습니다.")