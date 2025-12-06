# setdb.py
import sqlite3
import streamlit as st
from app_details.cleandata_fixfile import (
    upload_preclean, get_table_list, export_table_to_df
)

DB_PATH = "codefarmdb.sqlite"


def show_setdb():
    st.title("🛢️ DB 관리")

    st.markdown("---")
    st.subheader("📤 데이터 업로드")

    # 상태 초기화
    if "preview_df" not in st.session_state:
        st.session_state.preview_df = None
    if "preview_file_name" not in st.session_state:
        st.session_state.preview_file_name = None
    if "uploaded_info" not in st.session_state:
        st.session_state.uploaded_info = None

    uploaded_file = st.file_uploader("데이터 파일 업로드", type=["csv", "xlsx"])

    # 1) 파일이 새로 올라왔는지 체크
    if uploaded_file is None:
        # 파일이 아예 없으면 미리보기도 초기화
        st.session_state.preview_df = None
        st.session_state.preview_file_name = None

    else:
        # 파일 이름이 바뀌었으면(=다른 파일 업로드) 미리보기 초기화 후 다시 생성
        if uploaded_file.name != st.session_state.preview_file_name:
            table_name, enc_used, df_preview = upload_preclean(
                uploaded_file,
                save_to_db=False,   # 미리보기만
            )
            st.session_state.preview_df = df_preview
            st.session_state.preview_file_name = uploaded_file.name
            st.session_state.preview_enc = enc_used

    # 2) 미리보기: 파일이 있고, 아직 업로드 전일 때만 표시
    if st.session_state.preview_df is not None:
        st.write("데이터 미리보기 (업로드 전 확인용)")
        st.dataframe(st.session_state.preview_df, use_container_width=True)
        st.caption(f"인코딩: {st.session_state.preview_enc}")

        # 3) 업로드 확정 버튼
        if st.button("업로드하기"):
            table_name, enc_used, df_for_db = upload_preclean(
                uploaded_file,
                save_to_db=True,    # 실제 DB 저장
            )
            st.session_state.uploaded_info = (table_name, enc_used)

            # 업로드 후에는 미리보기 숨김
            st.session_state.preview_df = None
            st.session_state.preview_file_name = None

            st.success(
                f"데이터가 DB에 저장되었습니다. 테이블명: {table_name}"
            )


    st.markdown("---")
    st.subheader("🗂️ DB 테이블 관리")

    tables = get_table_list(DB_PATH)
    if not tables:
        st.info("현재 DB에 저장된 테이블이 없습니다. 먼저 데이터를 업로드해 주세요.")
        return

    st.markdown("현재 DB에 저장된 테이블 목록입니다.")
    st.write(tables)

    selected_table = st.selectbox(
        "내용 확인 / 이름 변경 / 삭제할 테이블 선택",
        tables
    )

    db_df = None
    if selected_table:
        db_df, db_preview = export_table_to_df(selected_table, DB_PATH)
        st.write(f"**{selected_table}** 테이블 미리보기")
        st.dataframe(db_preview, width='stretch')

    st.markdown("---")
    st.subheader("✏️ 테이블 이름 변경")

    if selected_table:
        new_name = st.text_input(
            "새 테이블 이름 입력",
            value=selected_table,
            help="공백 / 특수문자는 피하고, 영문/숫자/언더스코어 사용을 권장합니다."
        )

        if st.button("✔️ 저장"):
            if not new_name.strip():
                st.warning("새 테이블 이름을 입력해 주세요.")
            elif new_name in tables and new_name != selected_table:
                st.warning("이미 존재하는 테이블 이름입니다. 다른 이름을 사용해 주세요.")
            else:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute(f"ALTER TABLE [{selected_table}] RENAME TO [{new_name}];")
                    conn.commit()
                    conn.close()
                    st.success(f"'{selected_table}' → '{new_name}' 으로 이름이 변경되었습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"이름 변경 중 오류가 발생했습니다: {e}")

    st.markdown("---")
    st.subheader("💣 테이블 삭제")

    st.markdown(
        "선택된 테이블을 DB에서 완전히 삭제합니다. "
        "삭제 후에는 되돌릴 수 없습니다."
    )

    if selected_table:
        if st.button(f"❌ '{selected_table}' 테이블 삭제하기"):
            try:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute(f"DROP TABLE IF EXISTS [{selected_table}];")
                conn.commit()
                conn.close()
                st.success(f"'{selected_table}' 테이블이 삭제되었습니다.")
                st.rerun()
            except Exception as e:
                st.error(f"테이블 삭제 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    show_setdb()
