# perdata.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_details.cleandata_fixfile import get_table_list, export_table_to_df
from app_details.perdata_report import generate_farm_report

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
    # DB에서 DataFrame 불러오기 (타임스탬프 정보 포함)
    # ------------------------------
    try:
        df, df_tail, timestamp_col = export_table_to_df(selected_table)
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return

    # ------------------------------
    # 🔴 타임스탬프 열 자동 인식 (메타데이터 우선 → 첫 번째 컬럼 → 사용자 선택)
    # ------------------------------
    timestamp_idx = None
    
    # 1단계: 메타데이터에서 타임스탬프 열 확인
    if timestamp_col and timestamp_col in df.columns:
        timestamp_idx = list(df.columns).index(timestamp_col)
        st.info(f"타임스탬프: **{timestamp_col}**")
        try:
            df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
            df = df.set_index(timestamp_col)
            df.index.name = "Timestamp"
        except Exception as e:
            st.warning(f"타임스탬프 변환 실패: {e}. 수동 선택 필요")
            timestamp_col = None
    
    # 3단계: 사용자 수동 선택 (최후의 수단)
    if timestamp_col is None:
        col_options = df.columns.tolist()
        timestamp_col_manual = st.selectbox(
            "타임스탬프 열 선택",
            options=col_options,
            index=0,
            help="날짜/시간이 들어있는 열을 선택하세요"
        )
        try:
            df[timestamp_col_manual] = pd.to_datetime(df[timestamp_col_manual], errors='coerce')
            df = df.set_index(timestamp_col_manual)
            df.index.name = "Timestamp"
            timestamp_col = timestamp_col_manual
            st.info(f"선택된 타임스탬프: **{timestamp_col}**")
        except Exception as e:
            st.error(f"선택한 '{timestamp_col_manual}' 열을 타임스탬프로 변환할 수 없습니다: {e}")
            st.dataframe(df.head(), width='stretch')
            return

    data = df

    if data.index.isna().all():
        st.error("Timestamp 변환에 실패했습니다. 파일의 타임스탬프 열에 올바른 날짜/시간 형식이어야 합니다.")
        st.dataframe(df.head(), width='stretch')
        return

    # ------------------------------
    # 날짜 선택 범위 생성
    # ------------------------------
    valid_dates = sorted(list(set(data.index.date)))
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
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    tab_data, tab_stats, tab_report = st.tabs(["📄 데이터", "📈 센서별 그래프", "📋 리포트 생성"])
    all_columns = filtered.columns.tolist()

    # ------------------------------------
    # 1) 데이터 탭
    # ------------------------------------
    with tab_data:
        st.subheader("📄 데이터 보기")

        if all_columns:
            selected_vars = st.multiselect(
                '표시할 센서 변수 선택',
                options=all_columns,
                default=all_columns[:6],
            )

            selected_vars = [v for v in selected_vars if v in filtered.columns]

            if selected_vars:
                display_df = filtered[selected_vars].copy()
                display_df.index.name = "Timestamp"
                st.dataframe(display_df, width='stretch')
                
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
    # 2) 스무딩/필터링 탭
    # ------------------------------------
    with tab_stats:
        st.subheader("📈 센서별 스무딩 & 필터링")
        
        if all_columns:
            # 필터링할 센서 선택
            filter_vars = st.multiselect(
                "필터링할 센서 선택",
                options=all_columns,
                default=all_columns[:3]
            )
            
            filter_vars = [v for v in filter_vars if v in filtered.columns]
            
            if filter_vars:
                # 스무딩 파라미터 설정
                col1, col2, col3 = st.columns(3)
                with col1:
                    window_size = st.slider("이동평균 창 크기", 3, 50, 10, 1)
                with col2:
                    smooth_method = st.selectbox(
                        "스무딩 방법",
                        ["이동평균", "가우시안 필터", "저역통과 필터"],
                        index=0
                    )
                with col3:
                    st.markdown("<div style='height:33px;'></div>", unsafe_allow_html=True)
                    show_original = st.checkbox("원본 데이터와 비교", value=True)
                
                # 결과 표시 영역
                for var in filter_vars:
                    st.divider()
                    st.markdown(f"### `{var}` 필터링 결과")
                    
                    series = filtered[var].dropna()
                    if len(series) < window_size:
                        st.warning(f"`{var}` 데이터가 부족합니다.")
                        continue
                    
                    # 스무딩 적용
                    if smooth_method == "이동평균":
                        smoothed = series.rolling(window=window_size, center=True).mean()
                    elif smooth_method == "가우시안 필터":
                        try:
                            from scipy.ndimage import gaussian_filter1d
                            smoothed = pd.Series(
                                gaussian_filter1d(series.values, sigma=window_size/5),
                                index=series.index
                            )
                        except ImportError:
                            st.warning("scipy가 설치되지 않았습니다. pip install scipy")
                            continue
                    else:  # 저역통과 필터
                        try:
                            from scipy.signal import butter, filtfilt
                            b, a = butter(2, 0.1, btype='low')
                            smoothed = pd.Series(
                                filtfilt(b, a, series.values),
                                index=series.index
                            )
                        except ImportError:
                            st.warning("scipy가 설치되지 않았습니다. pip install scipy")
                            continue
                    
                    # 그래프 생성
                    fig = go.Figure()
                    if show_original:
                        fig.add_trace(go.Scatter(
                            x=series.index, y=series.values,
                            mode='lines', name='원본', line=dict(color="#FF6B6B")
                        ))
                    fig.add_trace(go.Scatter(
                        x=smoothed.index, y=smoothed.values,
                        mode='lines', name='스무딩', line=dict(color="#1E88E5", width=3)
                    ))
                    
                    fig.update_layout(
                        title=f"{smooth_method}",
                        xaxis_title='시간', yaxis_title=var,
                        height=300, hovermode='x unified'
                    )
                    st.plotly_chart(fig, width='stretch')
                    
                    # 다운로드 버튼
                    smoothed_df = pd.DataFrame({
                        '원본': series, f'{smooth_method}_{window_size}': smoothed
                    })
                    csv = smoothed_df.to_csv().encode('utf-8')
                    st.download_button(
                        label=f":material/download: {var} 필터링 데이터 다운로드",
                        data=csv,
                        file_name=f"{selected_table}_{var}_smoothed.csv",
                        mime='text/csv'
                    )
            else:
                st.info("필터링할 센서를 1개 이상 선택하세요.")
        else:
            st.warning("데이터가 없습니다.")

    # ------------------------------------
    # 3) 리포트 탭 (모듈 호출)
    # ------------------------------------
    with tab_report:
        generate_farm_report(filtered, selected_table, start_date, end_date, all_columns)

if __name__ == "__main__":
    show_perdata()
