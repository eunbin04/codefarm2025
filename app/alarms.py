# app/alarms.py
import streamlit as st
import pandas as pd
import time
import sqlite3
import warnings

from app_details.alarms_db import (
    initialize_alarms_db,
    load_alarm_data_from_db,
    update_alarm_correction_with_value,
    color_status,
    ALARMS_DB_PATH,
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
        st.caption(
            f"마지막 갱신: {last_update_str} (자동: 60초 간격)"
        )
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
        st.info("📭 아직 등록된 알림이 없습니다.")
        st.caption("배치에서 이상치가 탐지되면 여기에 기록됩니다.")

    # 5. 보정 상태 필터
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
        # 수집일 + 알림 유형 조합으로 선택하면 더 명확
        filtered_df = filtered_df.copy()
        filtered_df["키"] = (
            filtered_df["수집일"] + " | " + filtered_df["알림 유형"]
        )
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
                <div style="border: 2px solid {border_color}; border-radius: 10px; padding: 20px; background-color: #f9f9f9; margin-bottom: 20px;">
                    <h3 style="margin-top: 0;">{selected_row['알림 유형']} 알림</h3>
                    <p><b> - 수집일:</b> {selected_row['수집일']}</p>
                    <p><b> - 실제 값:</b> {selected_row['실제 값']}</p>
                    <p><b> - 상태:</b> {selected_row['상태']}</p>
                    <p><b> - 보정내역:</b> {selected_row['보정내역'] or '미보정'}</p>
                    <p><b> - 보정값:</b> {보정값}</p>
                    <p><b> - 보정 상세:</b><br>
                        <span style="font-size: 13px; color: #555;">
                            {selected_row.get('보정상세', '보정 상세 정보 없음')}
                        </span>
                    </p>
                    <p><b> - 설명:</b> {selected_row.get('설명', '설명 없음')}</p>
                    <p><b> - DB 기록 시각(KST):</b> {selected_row.get('생성시각(KST)', '정보 없음')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 수동 보정 버튼 (DB에는 상태/값/상세만 반영, 값은 사용자가 직접 입력하도록 할 수도 있음)
            if not is_corrected:
                if st.button("✋ 수동 보정", key=f"manual_{selected_key}"):
                    now_kst_str = get_korea_time().strftime("%Y-%m-%d %H:%M:%S (KST)")
                    cs = f"수동 보정 ({now_kst_str})"
                    cd = "사용자가 대시보드에서 수동 보정으로 처리했습니다."
                    cv = selected_row["실제 값"]  # 필요하면 다른 값으로 교체 가능

                    updated = update_alarm_correction_with_value(
                        selected_row["수집일"],
                        selected_row["알림 유형"],
                        cs,
                        cv,
                        cd,
                    )

                    if updated:
                        st.success("수동 보정 상태로 변경되었습니다.")
                        # 메모리 데이터도 갱신
                        idx = df_alarms[
                            (df_alarms["수집일"] == selected_row["수집일"])
                            & (df_alarms["알림 유형"] == selected_row["알림 유형"])
                        ].index[0]
                        df_alarms.at[idx, "보정내역"] = cs
                        df_alarms.at[idx, "보정상세"] = cd
                        df_alarms.at[idx, "보정값"] = cv
                        st.session_state.alarm_data = df_alarms
                    else:
                        st.error("수동 보정 상태 저장에 실패했습니다.")
    else:
        st.info("상세를 볼 알림이 없습니다.")

    # 9. 보정된 센서 데이터 미리보기
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
