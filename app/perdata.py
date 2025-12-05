# perdata.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from app_details.cleandata_fixfile import (
    upload_preclean,
    get_table_list,
    export_table_to_df, 
)


def show_perdata():

    st.title('📅 기간별 데이터')
    st.caption("농가 센서 데이터를 원하는 기간 동안 조회·통계·그래프로 확인할 수 있습니다.")

    st.markdown("---")

    tables = get_table_list()
    if not tables:
        st.warning("DB에 저장된 파일이 없습니다. 먼저 파일을 업로드하세요.")
        return

    selected_table = st.selectbox("데이터 파일 선택", tables)

    # ------------------------------
    # DB에서 DataFrame 불러오기 (tuple 반환이므로 첫 원소만 사용)
    # ------------------------------
    try:
        df, df_tail = export_table_to_df(selected_table)
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return

    # ------------------------------
    # 무조건 첫 번째 컬럼을 Timestamp로 지정
    # ------------------------------
    try:
        timestamp_col = df.columns[0]
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
        df = df.set_index(timestamp_col)
        df.index.name = "Timestamp"
    except:
        st.error("첫 번째 컬럼을 Timestamp로 변환할 수 없습니다.\nCSV/Excel 파일의 첫 컬럼이 시간이어야 합니다.")
        st.dataframe(df.head(), width='stretch')
        return

    data = df

    if data.index.isna().all():
        st.error("Timestamp 변환에 실패했습니다. 파일의 첫 번째 컬럼이 날짜/시간이어야 합니다.")
        st.dataframe(df.head(), width='stretch')
        return

    # ------------------------------
    # 날짜 선택 범위 생성
    # ------------------------------
    valid_dates = sorted(list(set(df.index.date)))  # data 대신 df 사용
    if len(valid_dates) == 0:
        st.warning("Timestamp가 올바르지 않아 분석을 진행할 수 없습니다.")
        return

    min_date = valid_dates[0]
    max_date = valid_dates[-1]

    date_range = st.date_input(
        "조회할 기간 선택",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if isinstance(date_range, (tuple, list)):
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    # ------------------------------
    # 기간 필터링
    # ------------------------------
    filtered = data.loc[
        (data.index.date >= start_date) & (data.index.date <= end_date)
    ]
    filtered = filtered.dropna(axis=1, how='all')

    # ------------------------------
    # 탭 구성
    # ------------------------------
    tab_data, tab_stats, tab_detail = st.tabs(["📄 데이터", "📊 통계", "📈 상세 그래프"])
    all_columns = filtered.columns.tolist()

    # ------------------------------------
    # 1) 데이터 탭
    # ------------------------------------
    with tab_data:
        st.subheader("📄 데이터 다운로드")

        if all_columns:
            selected_vars = st.multiselect(
                '표시할 센서 변수 선택',
                options=all_columns,
                default=all_columns[:6],
            )

            selected_vars = [v for v in selected_vars if v in filtered.columns]

            if selected_vars:
                st.dataframe(filtered[selected_vars], width='stretch')
                csv = filtered[selected_vars].to_csv().encode('utf-8')

                st.download_button(
                    label=":material/download: CSV 다운로드",
                    data=csv,
                    file_name=f"{selected_table}_filtered.csv",
                    mime='text/csv'
                )
            else:
                st.info("변수를 1개 이상 선택해주세요.")
        else:
            st.warning("해당 기간에는 유효한 데이터가 없습니다.")

    # ------------------------------------
    # 2) 통계 탭
    # ------------------------------------
    with tab_stats:
        st.subheader("📊 통계 요약")

        if all_columns:
            stats_vars = st.multiselect(
                "통계 계산할 센서 선택",
                options=all_columns,
                default=all_columns[:6]
            )

            stats_vars = [v for v in stats_vars if v in filtered.columns]

            if stats_vars:
                desc = filtered[stats_vars].describe().T
                desc.rename(
                    columns={
                        'mean': '평균',
                        'min': '최소',
                        'max': '최대',
                        'std': '표준편차',
                        '25%': '1Q',
                        '50%': '중앙값',
                        '75%': '3Q'
                    },
                    inplace=True
                )
                st.dataframe(desc, width='stretch')
            else:
                st.info("통계 계산할 변수를 선택하세요.")
        else:
            st.warning("데이터가 없습니다.")

    # ------------------------------------
    # 3) 상세 그래프 탭
    # ------------------------------------
    with tab_detail:
        st.subheader("📈 변수별 상세 그래프")

        if all_columns:
            cols_btn = st.columns(4)
            for i, col_name in enumerate(all_columns):
                if cols_btn[i % 4].button(col_name):
                    st.session_state["detail_var"] = col_name

            detail_var = st.session_state.get("detail_var")

            if detail_var and detail_var in filtered.columns:
                st.markdown(f"### • 선택된 변수: `{detail_var}`")
                series = filtered[detail_var].dropna()

                if not series.empty:
                    Q1 = series.quantile(0.25)
                    Q3 = series.quantile(0.75)
                    IQR = Q3 - Q1
                    lower = Q1 - 1.5 * IQR
                    upper = Q3 + 1.5 * IQR

                    fig = go.Figure()

                    fig.add_trace(go.Scatter(
                        x=series.index,
                        y=series.values,
                        mode='lines',
                        name='값',
                        line=dict(color="#1E88E5")
                    ))

                    fig.add_trace(go.Scatter(
                        x=np.concatenate([series.index, series.index[::-1]]),
                        y=np.concatenate([[lower]*len(series),
                                          [upper]*len(series[::-1])]),
                        fill='toself',
                        fillcolor='rgba(100,200,100,0.2)',
                        line=dict(color='rgba(255,255,255,0)'),
                        hoverinfo="skip",
                        name='IQR 범위',
                    ))

                    fig.update_layout(
                        xaxis_title='시간',
                        yaxis_title=detail_var,
                        hovermode='x unified',
                        height=500
                    )

                    st.plotly_chart(fig, width='stretch')

                else:
                    st.info("해당 변수에 데이터가 없습니다.")

            else:
                st.info("아래 버튼에서 상세히 볼 변수를 선택하세요.")

        else:
            st.warning("데이터가 없습니다.")

