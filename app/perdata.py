# perdata.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np


def load_mcdata():
    df = pd.read_csv('data/mc.csv', encoding='utf-8')

    df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df.set_index('Timestamp', inplace=True)
    
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.replace(-32767, pd.NA, inplace=True)

    df = df.round(3)

    return df


def show_perdata():

    st.title('📅 기간별 데이터')
    st.caption("기간을 선택하고, 센서별로 데이터를 탐색해보세요.")

    st.markdown("---")

    data = load_mcdata()  # 전체 데이터 불러오기

    # 데이터가 있는 고유 날짜 리스트 생성
    available_dates = sorted(list(set(data.index.date)))
    
    # 최소, 최대 날짜 설정
    min_date = available_dates[0]
    max_date = available_dates[-1]

    # 사용자가 선택할 기본값: 전체 범위
    default_start = min_date
    default_end = max_date

    # 날짜 입력 받기 (달력 형태)
    date_range = st.date_input(
        "조회할 기간 선택",
        value=(default_start, default_end),
        min_value=min_date,
        max_value=max_date
    )

    # date_input에서 단일 날짜 선택 시를 대비해 튜플로 처리
    if isinstance(date_range, tuple) or isinstance(date_range, list):
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    # 날짜 범위에 맞게 데이터 필터링 (시간 포함 인덱스이므로 날짜 조건으로 필터)
    filtered = data.loc[
        (data.index.date >= start_date) & (data.index.date <= end_date)
    ]

    filtered = filtered.dropna(axis=1, how='all')

    st.markdown("")

    # ----------------- 탭 구성 -----------------
    tab_data, tab_stats, tab_detail = st.tabs(["📄 데이터", "📊 통계", "📈 상세 그래프"])

    # 공통: 선택 가능한 변수 리스트
    all_columns = filtered.columns.tolist()

    # 세션 상태로 '상세 보기용 변수' 유지
    if "detail_var" not in st.session_state:
        st.session_state["detail_var"] = None

    # ================== 1) 데이터 탭 ==================
    with tab_data:
        st.subheader("📄 데이터 다운로드")

        if all_columns:
            selected_vars = st.multiselect(
                '측정 변수 선택',
                options=all_columns,
                default=all_columns[: min(6, len(all_columns))]
            )

            # 비어있는 열 제거 후 남은 컬럼 리스트에 맞게 selected_vars 필터링
            selected_vars = [var for var in selected_vars if var in filtered.columns]

            if selected_vars:
                # 기간 내의 선택된 변수 전체 원본 데이터 CSV로 변환
                csv = filtered[selected_vars].to_csv().encode('utf-8')
                # 데이터 미리보기
                st.dataframe(
                    filtered[selected_vars].head(200),
                    use_container_width=True,
                )
                
                st.download_button(
                    label=":material/download: CSV 다운로드",
                    data=csv,
                    file_name='sensor_data.csv',
                    mime='text/csv'
                )


            else:
                st.warning("최소 1개의 변수를 선택해주세요.")
        else:
            st.warning("표시할 변수가 없습니다. 기간을 다시 선택해보세요.")

    # ================== 2) 통계 탭 ==================
    with tab_stats:
        st.subheader("📊 데이터 통계 요약")

        if all_columns:
            stats_vars = st.multiselect(
                "변수 선택",
                options=all_columns,
                default=all_columns[: min(6, len(all_columns))]
            )
            stats_vars = [v for v in stats_vars if v in filtered.columns]

            if stats_vars:
                desc = filtered[stats_vars].describe().T
                desc = desc[['mean', 'min', 'max', 'std', '25%', '50%', '75%']]
                desc.rename(
                    columns={
                        'mean': '평균',
                        'min': '최소',
                        'max': '최대',
                        'std': '표준편차',
                        '25%': '25분위',
                        '50%': '중앙값',
                        '75%': '75분위',
                    },
                    inplace=True,
                )
                st.dataframe(desc, use_container_width=True)
            else:
                st.info("통계를 볼 변수를 선택해주세요.")
        else:
            st.warning("표시할 변수가 없습니다. 기간을 다시 선택해보세요.")

    # ================== 3) 상세 그래프 탭 ==================
    with tab_detail:
        st.subheader("📈 변수별 상세 그래프")

        if all_columns:
            cols_btn = st.columns(4)
            for i, col_name in enumerate(all_columns):
                if cols_btn[i % 4].button(col_name):
                    st.session_state["detail_var"] = col_name

            detail_var = st.session_state.get("detail_var", None)
            if detail_var and detail_var in filtered.columns:
                st.markdown(f"#### 🎯 선택된 변수: `{detail_var}`")

                series = filtered[detail_var].dropna()
                if not series.empty:
                    # IQR 계산
                    Q1 = series.quantile(0.25)
                    Q3 = series.quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound_iqr = Q1 - 1.5 * IQR
                    upper_bound_iqr = Q3 + 1.5 * IQR

                    # Plotly 그래프 생성
                    fig = go.Figure()

                    # 시계열 라인 차트 추가
                    fig.add_trace(go.Scatter(
                        x=series.index,
                        y=series.values,
                        mode='lines',
                        name='값',
                        line=dict(color="#E53D3D")
                    ))

                    # IQR 범위 영역 채우기
                    fig.add_trace(go.Scatter(
                        x=np.concatenate([series.index, series.index[::-1]]),
                        y=np.concatenate([[lower_bound_iqr]*len(series), [upper_bound_iqr]*len(series[::-1])]),
                        fill='toself',
                        fillcolor='rgba(197, 226, 181, 0.3)',
                        line=dict(color='rgba(255,255,255,0)'),
                        hoverinfo="skip",
                        showlegend=True,
                        name='IQR 범위',
                    ))

                    fig.update_layout(
                        xaxis_title='시간',
                        yaxis_title=detail_var,
                        hovermode='x unified'
                    )

                    st.plotly_chart(fig, use_container_width=True)

                else:
                    st.info("선택한 변수에 데이터가 없습니다.")
            else:
                st.info("상세히 보고 싶은 변수를 위에서 선택해주세요.")
        else:
            st.warning("표시할 변수가 없습니다. 기간을 다시 선택해보세요.")