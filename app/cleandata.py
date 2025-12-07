# app/cleandata.py
import streamlit as st
import io
import time
import pandas as pd
from app_details.cleandata_train import train_and_fix
from app_details.cleandata_fixfile import get_table_list, export_table_to_df


def show_cleandata():
    st.title("🛠️ 데이터 보정")

    st.markdown("---")
    st.subheader("✨ 클린 데이터 다운로드")

    tables = get_table_list()
    selected_table = st.selectbox("DB에 저장된 데이터 중 보정할 파일 선택", tables)
    db_df = None
    if selected_table:
        db_df, db_preview = export_table_to_df(selected_table)
        st.write("선택한 데이터 미리보기")
        st.dataframe(db_preview)

    target_df = db_df if db_df is not None else None

    col1, col2, col3 = st.columns(3)
    col_count = len(target_df.columns) if target_df is not None else 0
    with col1:
        t_location = st.number_input(
            "온도 인덱스",
            min_value=0, max_value=col_count - 1, value=1
        )
    with col2:
        h_location = st.number_input(
            "습도 인덱스",
            min_value=0, max_value=col_count - 1, value=3
        )
    with col3:
        r_location = st.number_input(
            "광 인덱스",
            min_value=0, max_value=col_count - 1, value=4
        )

    if st.button("보정하기"):
        if target_df is None:
            st.warning("먼저 파일 업로드 또는 DB에서 파일을 선택해 주세요.")
        else:
            # 1) 모델 학습 → 2) 이상치 탐지+보정
            df_fixed, msg = train_and_fix(
                target_df,
                t_location,   # 온도 인덱스
                h_location,   # 습도 인덱스
                r_location    # 광 인덱스
            )

            st.success("보정 작업이 완료되었습니다!")
            st.info(msg)
            st.write("보정된 데이터 미리보기(끝에서 5행)")
            st.dataframe(df_fixed.tail())

            
            
            with st.spinner("클린 데이터 생성 중..."):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_fixed.to_excel(writer, index=False)
                output.seek(0)
            st.download_button(
                label=":material/download: 보정된 데이터 다운로드",
                data=output.read(),
                file_name=f"{selected_table}_cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


if __name__ == "__main__":
    show_cleandata()
