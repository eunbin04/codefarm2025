# cleandata.py
import streamlit as st
from app_details.cleandata_train import manual_train, start_scheduler, stop_scheduler, get_train_log
from app_details.cleandata_fixfile import upload_preclean, process_file, get_table_list, export_table_to_file
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

    # 1. 파일 업로드
    uploaded_file = st.file_uploader("데이터 파일 업로드", type=['csv','xlsx'])
    file_path, enc_used, df_preview = upload_preclean(uploaded_file)

    if df_preview is not None:
        st.write("전처리된 데이터 미리보기(끝에서 5행)")
        st.dataframe(df_preview)
        st.success(f"데이터가 DB에 저장되었습니다! (인코딩: {enc_used})")

    # 2. DB에 저장된 파일 선택 후 불러오기
    tables = get_table_list()
    selected_table = st.selectbox("DB에 저장된 데이터 중 보정할 파일 선택", tables)

    db_file_path = None
    if selected_table:
        db_file_path, df_preview2 = export_table_to_file(selected_table)
        st.write("선택한 DB 데이터 미리보기(끝에서 5행)")
        st.dataframe(df_preview2)

    # 보정 대상 파일 경로 결정 (업로드 or DB 선택)
    target_file_path = file_path if file_path else db_file_path

    if st.button("보정하기"):
        if not target_file_path:
            st.warning("먼저 파일 업로드 또는 DB에서 파일을 선택해 주세요.")
        else:
            with st.spinner("파일 보정 중..."):
                fixed_file, msg = process_file(target_file_path)
            st.success("보정 작업이 완료되었습니다!")
            st.info(msg)

            if fixed_file is not None and os.path.exists(fixed_file):
                with open(fixed_file, 'rb') as f:
                    st.download_button(
                        label=":material/download: 클린 데이터 다운로드",
                        data=f.read(),
                        file_name="clean_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

if __name__ == "__main__":
    show_cleandata()
