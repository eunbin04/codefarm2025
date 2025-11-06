# cleandata.py
import streamlit as st
import subprocess
import datetime as datetime

def show_cleandata():
    st.title("📈 대시보드")

    st.markdown("### 모델 학습 이력 보기")

    # 실행 버튼 만들기
    if st.button("모델 학습 코드 실행"):
        with st.spinner("모델 학습 중... 잠시만 기다려주세요"):
            # 외부 스크립트 실행 (경로는 실제 상황에 맞게 조절)
            result = subprocess.run(
                ["python3", "outlier_fix/train_models.py"],
                capture_output=True,
                text=True
            )

            # 출력 결과 보여주기
            if result.returncode == 0:
                st.success("모델 학습 및 저장 완료!")
                st.text(result.stdout)
                st.text(result.stderr)
            else:
                st.error("학습 실행 중 오류 발생!")
                st.text(result.stdout)
                st.text(result.stderr)

    # 실행 이력(예: 로그파일이나 DB 기반)을 여기서 불러와 보여주기 (예시)
    # 이 예시는 파일에 쌓인 학습 로그를 보여주는 구조입니다.
    try:
        with open("outlier_fix/train_log.txt", "r") as f:
            log_content = f.read()
        st.markdown("### 이전 학습 실행 로그")
        st.text(log_content)
    except FileNotFoundError:
        st.info("아직 실행 로그가 없습니다.")