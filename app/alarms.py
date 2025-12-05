# app/alarms.py
import streamlit as st
import pandas as pd
import time
import warnings

from app_details.alarms_db import (
    initialize_alarms_db,
    load_alarm_data_from_db,
    update_alarm_correction_with_value,
    color_status,
    get_korea_time,
)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def show_alarms():
    # 1. DB 초기화
    if "alarms_db_initialized" not in st.session_state:
        initialize_alarms_db()
        st.session_state.alarms_db_initialized = True

    st.title("🚨 알림 기록")
    st.markdown("---")

    # 2. 새로고침/자동갱신 상태 관리
    if "alarms_last_update" not in st.session_state:
        st.session_state.alarms_last_update = 0

    manual_refresh = st.button("🔄 새로고침")

    now_ts = time.time()

    if manual_refresh or (now_ts - st.session_state.alarms_last_update > 60):
        st.session_state.alarm_data = load_alarm_data_from_db()
        st.session_state.alarms_last_update = now_ts

    if "alarm_data" not in st.session_state:
        st.session_state.alarm_data = load_alarm_data_from_db()

    df_alarms = st.session_state.alarm_data

    # 3. 상단 갱신 시간 표시
    if st.session_state.alarms_last_update > 0:
        korea_time = get_korea_time()
        last_update_str = korea_time.strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"마지막 갱신: {last_update_str} (자동: 60초 간격)")
    else:
        st.caption("초기 로딩 중...")

    # 4. KPI
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
        st.info("아직 등록된 알림이 없습니다.")
        st.caption("배치에서 이상치가 탐지되면 여기에 기록됩니다.")

    # 5. 필터 영역 (보정 상태 + 상태)
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        correction_filter = st.selectbox(
            "보정 상태 선택",
            ["전체", "미보정", "자동 보정", "수동 보정"],
        )

    with col_f2:
        status_filter = st.selectbox(
            "알림 상태 선택",
            ["전체", "이상치", "결측치"],
        )

    # 5-1. 보정 상태 필터 적용
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

    # 5-2. 상태(이상치/결측치) 필터 추가 적용
    if not filtered_df.empty and status_filter != "전체":
        filtered_df = filtered_df[filtered_df["상태"] == status_filter]

    # 6. 시간 정렬 (수집일 기준)
    if not filtered_df.empty and "수집일" in filtered_df.columns:
        filtered_df = filtered_df.copy()
        filtered_df["수집일_dt"] = pd.to_datetime(
            filtered_df["수집일"], format="%Y-%m-%d %H:%M", errors="coerce"
        )
        filtered_df = filtered_df.sort_values("수집일_dt", ascending=False)
        filtered_df = filtered_df.drop(columns=["수집일_dt"])

    # 7. 스타일링
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

    # 8. 상세 영역
    st.markdown("---")
    st.subheader("🔍 알림 상세")

    if not filtered_df.empty:
        filtered_df = filtered_df.copy()
        filtered_df["키"] = filtered_df["수집일"] + " | " + filtered_df["알림 유형"]
        keys = filtered_df["키"].tolist()

        selected_key = st.selectbox(
            "알림 선택",
            options=keys,
            help="선택한 알림의 상세 내용을 확인합니다.",
        )

        if selected_key:
            selected_row = filtered_df[filtered_df["키"] == selected_key].iloc[0]
            is_corrected = bool(selected_row["보정내역"])
            border_color = "#66C87F" if is_corrected else "lightcoral"

            보정값 = (
                selected_row["보정값"]
                if pd.notna(selected_row["보정값"])
                else "보정값 없음"
            )

            st.markdown(
                f"""
                <div style="border: 2px solid {border_color}; border-radius: 10px; padding: 20px; background-color: {"#f8f8f8"}; margin-bottom: 20px;">
                    <h3 style="margin-top: 0;">{selected_row['알림 유형']} 알림</h3>
                    <p><b> - 수집일:</b> {selected_row['수집일']}</p>
                    <p><b> - 실제 값:</b> {selected_row['실제 값']}</p>
                    <p><b> - 상태:</b> {selected_row['상태']}</p>
                    <p><b> - 보정내역:</b> {selected_row['보정내역'] or '미보정'}</p>
                    <p><b> - 보정값:</b> {보정값}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 수동 보정 버튼
            if not is_corrected:
                if st.button("✋ 수동 보정", key=f"manual_{selected_key}"):
                    now_kst_str = get_korea_time().strftime("%Y-%m-%d %H:%M:%S (KST)")
                    cs = f"수동 보정 ({now_kst_str})"
                    cd = "사용자가 대시보드에서 수동 보정으로 처리했습니다."
                    cv = selected_row["실제 값"]

                    updated = update_alarm_correction_with_value(
                        selected_row["수집일"],
                        selected_row["알림 유형"],
                        cs,
                        cv,
                        cd,
                    )

                    if updated:
                        st.success("수동 보정 상태로 변경되었습니다.")
                        idx = df_alarms[
                            (df_alarms["수집일"] == selected_row["수집일"])
                            & (df_alarms["알림 유형"] == selected_row["알림 유형"])
                        ].index[0]
                        df_alarms.at[idx, "보정내역"] = cs
                        df_alarms.at[idx, "보정값"] = cv
                        st.session_state.alarm_data = df_alarms
                        st.rerun()
                    else:
                        st.error("수동 보정 상태 저장에 실패했습니다.")
    else:
        st.info("상세를 볼 알림이 없습니다.")
