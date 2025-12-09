# app/cleandata.py
import streamlit as st
import io
import time
import pandas as pd
import plotly.express as px

from app_details.cleandata_train import train_and_fix
from app_details.cleandata_fixfile import get_table_list, export_table_to_df


def show_cleandata():
    st.title("🛠️ 데이터 보정")

    st.markdown("---")
    st.subheader("✨ 클린 데이터 다운로드")

    tables = get_table_list()
    selected_table = st.selectbox("DB에 저장된 데이터 중 보정할 파일 선택", tables)
    db_df = None
    timestamp_col_idx = None
    timestamp_col = None

    if selected_table:
        db_df, db_preview, timestamp_col = export_table_to_df(selected_table)
        st.write("선택한 데이터 미리보기")
        st.dataframe(db_preview, use_container_width=True)

        if timestamp_col and timestamp_col in db_df.columns:
            timestamp_col_idx = list(db_df.columns).index(timestamp_col)

    target_df = db_df if db_df is not None else None

    col1, col2, col3, col4 = st.columns(4)
    col_count = len(target_df.columns) if target_df is not None else 0

    with col1:
        if timestamp_col_idx is not None:
            st.markdown("<div style='height:0px;'></div>", unsafe_allow_html=True)
            st.info(f"타임스탬프 인덱스: **{timestamp_col}** (**{timestamp_col_idx}**)")
        else:
            ts_input = st.number_input(
                "타임스탬프 인덱스",
                min_value=0,
                max_value=max(col_count - 1, 0),
                value=0,
            )

    with col2:
        t_location = st.number_input(
            "온도 인덱스",
            min_value=0,
            max_value=max(col_count - 1, 0),
            value=1,
        )
    with col3:
        h_location = st.number_input(
            "습도 인덱스",
            min_value=0,
            max_value=max(col_count - 1, 0),
            value=3,
        )
    with col4:
        r_location = st.number_input(
            "광 인덱스",
            min_value=0,
            max_value=max(col_count - 1, 0),
            value=4,
        )

    if st.button("보정하기", type="primary"):
        if target_df is None:
            st.warning("먼저 파일 업로드 또는 DB에서 파일을 선택해 주세요.")
        else:
            timestamp_idx = timestamp_col_idx if timestamp_col_idx is not None else 0

            original_df = target_df.copy()

            df_fixed, msg = train_and_fix(
                target_df,
                t_location,
                h_location,
                r_location,
                timestamp_idx,
            )

            st.success("보정 작업이 완료되었습니다!")
            st.info(msg)

            cols = original_df.columns.tolist()
            t_col = cols[t_location]
            h_col = cols[h_location]
            r_col = cols[r_location]

            fixed_t = pd.to_numeric(df_fixed[t_col], errors="coerce")
            fixed_h = pd.to_numeric(df_fixed[h_col], errors="coerce")
            fixed_r = pd.to_numeric(df_fixed[r_col], errors="coerce")

            orig_t = pd.to_numeric(original_df[t_col], errors="coerce")
            orig_h = pd.to_numeric(original_df[h_col], errors="coerce")
            orig_r = pd.to_numeric(original_df[r_col], errors="coerce")

            temp_outliers = ((~orig_t.isna()) & fixed_t.isna()).sum()
            humi_outliers = ((~orig_h.isna()) & fixed_h.isna()).sum()
            light_outliers = ((~orig_r.isna()) & fixed_r.isna()).sum()

            st.markdown("#### 이상치 탐지 개수")
            c1, c2, c3 = st.columns(3)
            c1.metric("온도 이상치", f"{temp_outliers} 개")
            c2.metric("습도 이상치", f"{humi_outliers} 개")
            c3.metric("광(조도) 이상치", f"{light_outliers} 개")

            st.markdown("---")
            st.subheader("📈 원본 vs 보정값 비교")

            time_col = cols[timestamp_idx]
            time_series = pd.to_datetime(original_df[time_col], errors="coerce")

            def plot_compare(col_name, label):
                orig = pd.to_numeric(original_df[col_name], errors="coerce")
                fixed = pd.to_numeric(df_fixed[col_name], errors="coerce")

                plot_df = pd.DataFrame({
                    "time": time_series,
                    "원본": orig,
                    "보정": fixed,
                }).dropna(subset=["time"])

                fig = px.line(
                    plot_df,
                    x="time",
                    y=["원본", "보정"],
                    title=f"{label} 원본 vs 보정",
                )
                # 🔴 기간 선택 range slider 추가
                fig.update_layout(
                    xaxis=dict(
                        rangeselector=dict(
                            buttons=list([
                                dict(count=1, label="1d", step="day", stepmode="backward"),
                                dict(count=7, label="1w", step="day", stepmode="backward"),
                                dict(count=1, label="1m", step="month", stepmode="backward"),
                                dict(step="all", label="All"),
                            ])
                        ),
                        rangeslider=dict(visible=True),
                        type="date",
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)

            plot_compare(t_col, "온도")
            plot_compare(h_col, "습도")
            plot_compare(r_col, "광(조도)")

            st.markdown("---")
            st.subheader("✨ 보정된 데이터 다운로드")

            st.write("보정된 데이터 미리보기(끝에서 5행)")
            st.dataframe(df_fixed.tail())

            with st.spinner("클린 데이터 생성 중..."):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df_fixed.to_excel(writer, index=False)
                output.seek(0)
            st.download_button(
                label=":material/download: 보정된 데이터 다운로드",
                data=output.read(),
                file_name=f"{selected_table}_cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


if __name__ == "__main__":
    show_cleandata()
