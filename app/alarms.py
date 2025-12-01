# app/alarms.py
import streamlit as st
import pandas as pd
import time
import sqlite3
import warnings

from app_details.alarms_db import (
    initialize_alarms_db,
    load_alarm_data_from_db,
    update_alarm_correction,
    color_status,
    ALARMS_DB_PATH,
    get_korea_time,
)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def show_alarms():
    # 1. DB 초기화 (세션당 한 번)
    if "alarms_db_initialized" not in st.session_state:
        initialize_alarms_db()
        st.session_state.alarms_db_initialized = True

    st.title("🚨 알림 기록")
    st.markdown("---")

    # 2. 새로고침/자동갱신 상태 관리
    if "alarms_last_update" not in st.session_state:
        st.session_state.alarms_last_update = 0

    # 상단 버튼 영역
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        manual_refresh = st.button("🔄 새로고침")

    now_ts = time.time()

    # 새로고침 버튼을 누르거나, 마지막 갱신 후 60초가 지났으면 다시 로딩
    if manual_refresh or (now_ts - st.session_state.alarms_last_update > 60):
        st.session_state.alarm_data = load_alarm_data_from_db()
        st.session_state.alarms_last_update = now_ts

    # 3. 데이터 없으면 로딩
    if "alarm_data" not in st.session_state:
        st.session_state.alarm_data = load_alarm_data_from_db()

    df_alarms = st.session_state.alarm_data

    # 4. 상단 갱신 시간 표시
    if st.session_state.alarms_last_update > 0:
        korea_time = get_korea_time()
        last_update_str = korea_time.strftime("%Y-%m-%d %H:%M:%S")
        st.caption(
            f"마지막 갱신: {last_update_str} (자동: 60초 간격)"
        )
    else:
        st.caption("초기 로딩 중...")
    

    # 5. 상단 KPI
    if not df_alarms.empty:
        total = len(df_alarms)
        uncorrected = (df_alarms["보정내역"] == "").sum()
        auto_corr = df_alarms["보정내역"].str.contains("자동 보정", na=False).sum()
        manual_corr = df_alarms["보정내역"].str.contains("수동 보정", na=False).sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 알림", total)
        c2.metric("미보정", uncorrected, delta_color="inverse")
        c3.metric("자동 보정", auto_corr)
        c4.metric("수동 보정", manual_corr)
    else:
        st.info("📭 아직 등록된 알림이 없습니다.")
        st.caption("배치에서 이상치가 탐지되면 여기에 기록됩니다.")

    # 6. 보정 상태 필터
    correction_filter = st.selectbox(
        "보정 상태 선택",
        ["전체", "미보정", "자동 보정", "수동 보정"],
    )

    if not df_alarms.empty:
        if correction_filter == "자동 보정":
            filtered_df = df_alarms[
                df_alarms["보정내역"].str.contains("자동 보정", na=False)
            ]
        elif correction_filter == "수동 보정":
            filtered_df = df_alarms[
                df_alarms["보정내역"].str.contains("수동 보정", na=False)
            ]
        elif correction_filter == "미보정":
            filtered_df = df_alarms[df_alarms["보정내역"] == ""]
        else:
            filtered_df = df_alarms.copy()
    else:
        filtered_df = pd.DataFrame(
            columns=df_alarms.columns if not df_alarms.empty else []
        )

    # 7. 시간 정렬 (최신순)
    if not filtered_df.empty and "시간" in filtered_df.columns:
        filtered_df = filtered_df.copy()
        filtered_df["시간_dt"] = pd.to_datetime(
            filtered_df["시간"], format="%Y-%m-%d %H:%M", errors="coerce"
        )
        filtered_df = filtered_df.sort_values("시간_dt", ascending=False)
        filtered_df = filtered_df.drop(columns=["시간_dt"])

    # 8. 스타일링 및 목록 표시
    if not filtered_df.empty:
        def apply_color(row):
            return [
                color_status(row["상태"], row["보정내역"]) if col == "상태" else ""
                for col in filtered_df.columns
            ]

        styled_df = filtered_df.style.apply(apply_color, axis=1)
    else:
        styled_df = filtered_df

    st.subheader("📋 알림 목록")
    st.dataframe(styled_df, hide_index=True, width="stretch")

    # 9. 상세 영역
    st.markdown("---")
    st.subheader("🔍 알림 상세")

    if not filtered_df.empty:
        alert_times = filtered_df["시간"].drop_duplicates().tolist()
        selected_time = st.selectbox(
            "알림 선택",
            options=alert_times,
            help="선택한 알림의 상세 내용을 확인합니다.",
        )

        if selected_time:
            selected_row = df_alarms[df_alarms["시간"] == selected_time].iloc[0]
            is_corrected = bool(selected_row["보정내역"])
            border_color = "#66C87F" if is_corrected else "lightcoral"

            correction_detail = selected_row.get("보정상세", "")
            description = selected_row.get("설명", "설명 없음")

            st.markdown(
                f"""
                <div style="border: 2px solid {border_color}; border-radius: 10px; padding: 20px; background-color: #f9f9f9; margin-bottom: 20px;">
                    <h3 style="margin-top: 0;">{selected_row['알림 유형']} 알림</h3>
                    <p><b> - 발생 시간:</b> {selected_row['시간']}</p>
                    <p><b> - 상태:</b> {selected_row['상태']}</p>
                    <p><b> - 상세 설명:</b> {description}</p>
                    <hr>
                    <p><b> - 보정 상태:</b> {selected_row['보정내역'] or '미보정'}</p>
                    <p><b> - 보정 상세:</b><br><span style="font-size: 13px; color: #555;">{correction_detail or '보정 상세 정보 없음'}</span></p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 수동 보정 버튼
            if not is_corrected:
                if st.button("✋ 이 알림 수동 보정 처리", key=f"manual_{selected_time}"):
                    now_kst_str = get_korea_time().strftime("%Y-%m-%d %H:%M:%S (KST)")
                    cs = f"수동 보정 ({now_kst_str})"
                    cd = "사용자가 대시보드에서 수동 보정으로 처리했습니다."

                    if update_alarm_correction(selected_time, cs, cd):
                        st.success("수동 보정 상태로 변경되었습니다.")
                        # 메모리상의 데이터도 같이 수정
                        idx = df_alarms[df_alarms["시간"] == selected_time].index[0]
                        df_alarms.at[idx, "보정내역"] = cs
                        df_alarms.at[idx, "보정상세"] = cd
                        st.session_state.alarm_data = df_alarms
                    else:
                        st.error("수동 보정 상태 저장에 실패했습니다.")
    else:
        st.info("상세를 볼 알림이 없습니다.")

    # 10. 보정된 센서 데이터 미리보기
    with st.expander("📊 보정된 센서 데이터 미리보기"):
        try:
            conn = sqlite3.connect(ALARMS_DB_PATH)
            q = """
                SELECT
                    time_str,
                    humidity,
                    temperature,
                    irradiance,
                    source,
                    datetime(created_at, 'localtime') AS created_at
                FROM corrected_sensor
                ORDER BY created_at DESC
                LIMIT 10
            """
            prev_df = pd.read_sql(q, conn)
            conn.close()
            if not prev_df.empty:
                st.dataframe(prev_df, width="stretch")
            else:
                st.caption("아직 보정된 센서 데이터가 없습니다.")
        except Exception as e:
            st.error(f"보정 데이터 로드 중 오류: {e}")
