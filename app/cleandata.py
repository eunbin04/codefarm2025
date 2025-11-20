# cleandata.py
import streamlit as st
from app_details.cleandata_train import manual_train, start_scheduler, stop_scheduler, get_train_log
from app_details.cleandata_fixfile import upload_preclean, process_file
import os

def show_cleandata():
    st.title("✨ 클린 데이터")
    st.markdown("---")
    st.subheader("🎓 모델 학습")

    if st.button("▶️ 수동 학습 실행"):
        with st.spinner("모델 학습 중... 잠시만 기다려주세요"):
            msg = manual_train()
        st.success(msg)

    if st.button("🔄 자동 학습 시작"):
        st.success(start_scheduler())

    if st.button("⏹️ 자동 학습 중지"):
        st.success(stop_scheduler())

    st.markdown("#### 이전 학습 실행 로그")
    st.text(get_train_log())

    st.markdown("---")
    st.subheader("🛠️ 클린 데이터 다운로드")

    uploaded_file = st.file_uploader("데이터 파일 업로드", type=['csv','xlsx'])
    file_path, enc_used, df_preview = upload_preclean(uploaded_file)

    if df_preview is not None:
        st.write("전처리된 데이터 미리보기(끝에서 5행)")
        st.dataframe(df_preview)
        st.success(f"데이터가 DB에 저장되었습니다! (인코딩: {enc_used})")

    fixed_file = None
    msg = None

    if st.button("보정하기") and file_path is not None:
        with st.spinner("이상치 탐지 및 보정 중..."):
            fixed_file, msg = process_file(file_path)
        st.success("보정 작업이 완료되었습니다!")
        st.info(msg)

    if fixed_file is not None and os.path.exists(fixed_file):
        with open(fixed_file, 'rb') as f:
            data = f.read()
        st.download_button(
            label=":material/download: 클린 데이터 다운로드",
            data=data,
            file_name="clean_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    show_cleandata()
