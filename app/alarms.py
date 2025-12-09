import streamlit as st
import pandas as pd
import time
import warnings
import json

from app_details.alarms_db import (
    initialize_alarms_db,
    load_alarm_data_from_db,
    update_alarm_correction_with_value,
    color_status,
    get_korea_time,
    load_vpd_solution_alarms,
)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def show_alarms():
    # DB 초기화
    if "alarms_db_initialized" not in st.session_state:
        initialize_alarms_db()
        st.session_state.alarms_db_initialized = True

    st.title("🚨 알림 기록")
    st.markdown("---")

    # ===== 공통 KPI 영역: 총 알림 / 이상치 알림 / VPD 알림 =====
    # 이상치 알림 데이터 (세션 또는 새 로드)
    if "alarm_data" not in st.session_state:
        st.session_state.alarm_data = load_alarm_data_from_db()
    df_alarms_all = st.session_state.alarm_data

    # VPD 솔루션 데이터
    df_vpd_all = load_vpd_solution_alarms(limit=200)

    # 개수 계산
    num_outlier = len(df_alarms_all) if not df_alarms_all.empty else 0
    num_vpd = len(df_vpd_all) if not df_vpd_all.empty else 0
    num_total = num_outlier + num_vpd

    kc1, kc2, kc3 = st.columns(3)
    kc1.metric("총 알림", num_total)
    kc2.metric("이상치 알림", num_outlier)
    kc3.metric("VPD 알림", num_vpd)

    # 탭 영역
    tab_basic, tab_vpd = st.tabs(["이상치·결측 알림", "VPD 솔루션"])

    with tab_basic:
        show_basic_alarms_tab()

    with tab_vpd:
        show_vpd_solution_tab()

    st.divider()
    # 갱신 시간 표시
    if "alarms_last_update" in st.session_state and st.session_state.alarms_last_update > 0:
        korea_time = get_korea_time()
        last_update_str = korea_time.strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"마지막 갱신: {last_update_str}")
    else:
        st.caption("초기 로딩 중...")


def show_basic_alarms_tab():
    # 자동갱신 상태 관리
    if "alarms_last_update" not in st.session_state:
        st.session_state.alarms_last_update = 0

    now_ts = time.time()

    if (now_ts - st.session_state.alarms_last_update > 60):
        st.session_state.alarm_data = load_alarm_data_from_db()
        st.session_state.alarms_last_update = now_ts

    if "alarm_data" not in st.session_state:
        st.session_state.alarm_data = load_alarm_data_from_db()

    df_alarms = st.session_state.alarm_data

    # ==== 이 탭 전용 KPI (미보정/자동/수동) ====
    if not df_alarms.empty:
        total = len(df_alarms)
        uncorrected = (df_alarms["보정내역"] == "").sum()
        auto_corr = df_alarms["보정내역"].str.contains("자동 보정", na=False).sum()
        manual_corr = df_alarms["보정내역"].str.contains("수동 보정", na=False).sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("미보정", uncorrected, delta_color="inverse")
        c2.metric("자동 보정", auto_corr)
        c3.metric("수동 보정", manual_corr)
    else:
        st.info("아직 등록된 알림이 없습니다.")
        st.caption("배치에서 이상치가 탐지되면 여기에 기록됩니다.")

    # 필터
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

    # 보정 상태 필터
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

    # 상태 필터
    if not filtered_df.empty and status_filter != "전체":
        filtered_df = filtered_df[filtered_df["상태"] == status_filter]

    # 시간 정렬
    if not filtered_df.empty and "수집일" in filtered_df.columns:
        filtered_df = filtered_df.copy()
        filtered_df["수집일_dt"] = pd.to_datetime(
            filtered_df["수집일"], format="%Y-%m-%d %H:%M", errors="coerce"
        )
        filtered_df = filtered_df.sort_values("수집일_dt", ascending=False)
        filtered_df = filtered_df.drop(columns=["수집일_dt"])

    # 스타일링
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

    # 상세 영역
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
                <div style="border: 2px solid {border_color}; border-radius: 10px; padding: 20px; background-color: #f8f8f8; margin-bottom: 20px;">
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

            # 수동 보정
            if not is_corrected:
                if st.button("보정하기", key=f"manual_{selected_key}"):
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
                        idx = st.session_state.alarm_data[
                            (st.session_state.alarm_data["수집일"] == selected_row["수집일"])
                            & (st.session_state.alarm_data["알림 유형"] == selected_row["알림 유형"])
                        ].index[0]
                        st.session_state.alarm_data.at[idx, "보정내역"] = cs
                        st.session_state.alarm_data.at[idx, "보정값"] = cv
                        st.rerun()
                    else:
                        st.error("수동 보정 상태 저장에 실패했습니다.")
    else:
        st.info("상세를 볼 알림이 없습니다.")


def show_vpd_solution_tab():
    df_vpd = load_vpd_solution_alarms(limit=200)

    if df_vpd.empty:
        st.info("등록된 VPD 솔루션 알림이 없습니다.")
        return

    # 요약 표
    df_summary = df_vpd[["시간", "VPD", "온도", "습도", "전략"]].copy()
    st.subheader("💦 VPD 솔루션 목록")
    st.dataframe(df_summary, hide_index=True, width="stretch")

    # 상세 영역
    st.markdown("---")
    st.subheader("🔍 솔루션 상세")

    df_vpd = df_vpd.copy()
    df_vpd["키"] = df_vpd["시간"] + " | " + df_vpd["VPD"].round(2).astype(str)
    keys = df_vpd["키"].tolist()

    selected_key = st.selectbox(
        "솔루션 선택",
        options=keys,
        help="선택한 시점의 VPD 제어 솔루션 상세 정보를 확인합니다.",
    )

    if not selected_key:
        return

    row = df_vpd[df_vpd["키"] == selected_key].iloc[0]

    # 상세 JSON 파싱
    detail = {}
    if pd.notna(row["상세"]) and isinstance(row["상세"], str) and row["상세"].strip() != "":
        try:
            detail = json.loads(row["상세"])
        except Exception:
            detail = {}

    time_str = row["시간"]
    vpd = row["VPD"]
    T = row["온도"]
    H = row["습도"]
    summary = row["전략"]

    st.markdown(
        f"""
        <div style="border: 2px solid #4C9AFF; border-radius: 10px; padding: 20px; background-color: #f8f8f8; margin-bottom: 20px;">
            <h3 style="margin-top: 0;">VPD 제어 솔루션</h3>
            <p><b> - 시간:</b> {time_str}</p>
            <p><b> - 당시 상태:</b> T={T:.1f}°C, RH={H:.1f}%, VPD={vpd:.2f} kPa</p>
            <p><b> - 전략 요약:</b> {summary}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if detail:
        T_target = detail.get("T_target")
        RH_target = detail.get("RH_target")
        cooling_dT_C = detail.get("cooling_dT_C")
        water_L_per_m2 = detail.get("water_L_per_m2")
        q_sens = detail.get("q_sens_kWh_per_m2")
        q_lat = detail.get("q_lat_kWh_per_m2")
        q_tot = detail.get("q_tot_kWh_per_m2")

        st.markdown(
            f"""
            <div style="border: 2px solid #cccccc; border-radius: 8px; padding: 16px; background-color: #ffffff;">
                <p><b> - 목표 온도:</b> {T_target:.2f}°C (ΔT={cooling_dT_C:.2f}°C 냉방)</p>
                <p><b> - 목표 습도:</b> {RH_target:.1f}%</p>
                <p><b> - 가습량:</b> {water_L_per_m2:.3f} L/m²</p>
                <p><b> - 에너지:</b> 냉방 {q_sens:.4f} kWh/m², 가습 {q_lat:.4f} kWh/m², 총 {q_tot:.4f} kWh/m²</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.caption("상세 솔루션 정보가 없습니다.")
