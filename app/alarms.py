# alarms.py
import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime
import time


# 알림/보정 전용 DB 파일 (sensor_data.db와 분리)
ALARMS_DB_PATH = "alarms.db"
SETTINGS_FILE = "config/settings.json"


def load_settings():
    """settings.json에서 컬럼 인덱스 읽기"""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return settings
    else:
        return {
            "h_location": 3,
            "r_location": 4,
            "t_location": 1,
        }


def initialize_alarms_db():
    """alarms.db 안에 alarms와 corrected_sensor 테이블 생성"""
    conn = sqlite3.connect(ALARMS_DB_PATH)
    cursor = conn.cursor()

    # 알림 로그 테이블
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            alarm_type TEXT,
            status TEXT,
            correction_status TEXT,
            correction_detail TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # 보정된 센서 데이터 테이블
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS corrected_sensor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT,
            humidity REAL,
            temperature REAL,
            irradiance REAL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def load_alarm_data_from_db():
    """alarms.db의 alarms 테이블에서 알림 데이터 로드"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        query = """
            SELECT time_str, alarm_type, status, correction_status, correction_detail, description
            FROM alarms
            ORDER BY created_at DESC
            LIMIT 100
        """
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty:
            return pd.DataFrame(
                columns=["시간", "알림 유형", "상태", "보정내역", "보정상세", "설명"]
            )

        df.columns = ["시간", "알림 유형", "상태", "보정내역", "보정상세", "설명"]
        return df

    except Exception as e:
        st.error(f"알림 데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(
            columns=["시간", "알림 유형", "상태", "보정내역", "보정상세", "설명"]
        )


def save_alarm_to_db(alarm_data: dict):
    """
    alarm_data 예:
    {
        'time_str': '2025-11-30 14:02',
        'alarm_type': '온도',
        'status': '이상치',
        'correction_status': '',  # 처음엔 공백 (미보정)
        'correction_detail': '', # 나중에 predict.py msg를 넣음
        'description': '온도 센서 이상 또는 급변(비정상 패턴)'
    }
    """
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO alarms
            (time_str, alarm_type, status, correction_status, correction_detail, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alarm_data.get("time_str", ""),
                alarm_data.get("alarm_type", ""),
                alarm_data.get("status", ""),
                alarm_data.get("correction_status", ""),
                alarm_data.get("correction_detail", ""),
                alarm_data.get("description", ""),
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        st.error(f"알림 저장 중 오류 발생: {e}")
        return False


def update_alarm_correction(time_str: str, correction_status: str, correction_detail: str):
    """특정 시간의 알림을 보정 상태로 업데이트"""
    try:
        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE alarms
            SET correction_status = ?, correction_detail = ?
            WHERE time_str = ?
            """,
            (correction_status, correction_detail, time_str),
        )

        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    except Exception as e:
        st.error(f"알림 업데이트 중 오류 발생: {e}")
        return False


def save_corrected_sensor_data(corrected_df: pd.DataFrame):
    """
    배치/스케줄러에서 correct_last_row_outlier로 보정된 DataFrame을
    alarms.db의 corrected_sensor 테이블에 저장할 때 사용.
    sensor_data.db는 여기서 건드리지 않는다.
    """
    try:
        settings = load_settings()
        h_loc = settings.get("h_location", 3)
        r_loc = settings.get("r_location", 4)
        t_loc = settings.get("t_location", 1)

        cols = corrected_df.columns.tolist()
        time_col = cols[0]
        hum_col = cols[h_loc]
        rad_col = cols[r_loc]
        tmp_col = cols[t_loc]

        conn = sqlite3.connect(ALARMS_DB_PATH)
        cursor = conn.cursor()

        for _, row in corrected_df.iterrows():
            cursor.execute(
                """
                INSERT INTO corrected_sensor
                (time_str, humidity, temperature, irradiance, source, created_at)
                VALUES (?, ?, ?, ?, 'corrected', CURRENT_TIMESTAMP)
                """,
                (
                    str(row[time_col]),
                    float(row[hum_col]) if pd.notna(row[hum_col]) else None,
                    float(row[tmp_col]) if pd.notna(row[tmp_col]) else None,
                    float(row[rad_col]) if pd.notna(row[rad_col]) else None,
                ),
            )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        st.error(f"보정된 센서 데이터 저장 중 오류 발생: {e}")
        return False


def color_status(val, correction):
    """상태 컬럼 색상 스타일링"""
    if correction and correction != "":
        return "background-color: lightgreen;"  # 보정 완료
    return "background-color: lightcoral;"      # 미보정


def show_alarms():
    # DB 초기화 (최초 1회)
    if "alarms_db_initialized" not in st.session_state:
        initialize_alarms_db()
        st.session_state.alarms_db_initialized = True

    st.title("🚨 알림 기록")
    st.markdown("---")

    # 실시간 갱신 타이머
    if "alarms_last_update" not in st.session_state:
        st.session_state.alarms_last_update = 0

    now_ts = time.time()
    if now_ts - st.session_state.alarms_last_update > 60:
        st.session_state.alarm_data = load_alarm_data_from_db()
        st.session_state.alarms_last_update = now_ts
        st.rerun()

    # 데이터 로딩
    if "alarm_data" not in st.session_state:
        st.session_state.alarm_data = load_alarm_data_from_db()

    df_alarms = st.session_state.alarm_data

    # 마지막 갱신 시간 표시
    if st.session_state.alarms_last_update > 0:
        last_update_str = datetime.fromtimestamp(
            st.session_state.alarms_last_update
        ).strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"마지막 갱신: {last_update_str} (1분마다 자동 갱신)")
    else:
        st.caption("초기 로딩 중...")

    # 요약 메트릭
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

    # 보정 상태 필터
    correction_filter = st.selectbox(
        "보정 상태 선택", ["전체", "미보정", "자동 보정", "수동 보정"]
    )

    if not df_alarms.empty:
        if correction_filter == "자동 보정":
            filtered_df = df_alarms[df_alarms["보정내역"].str.contains("자동 보정", na=False)]
        elif correction_filter == "수동 보정":
            filtered_df = df_alarms[df_alarms["보정내역"].str.contains("수동 보정", na=False)]
        elif correction_filter == "미보정":
            filtered_df = df_alarms[df_alarms["보정내역"] == ""]
        else:
            filtered_df = df_alarms.copy()
    else:
        filtered_df = pd.DataFrame(columns=df_alarms.columns)

    # 시간 정렬 (최신순)
    if not filtered_df.empty and "시간" in filtered_df.columns:
        filtered_df = filtered_df.copy()
        filtered_df["시간_dt"] = pd.to_datetime(
            filtered_df["시간"], format="%Y-%m-%d %H:%M", errors="coerce"
        )
        filtered_df = filtered_df.sort_values("시간_dt", ascending=False)
        filtered_df = filtered_df.drop(columns=["시간_dt"])

    # 표 스타일링 (상태 컬럼 색상)
    if not filtered_df.empty:
        styled_df = filtered_df.style.apply(
            lambda row: [
                color_status(row["상태"], row["보정내역"]) if col == "상태" else ""
                for col in filtered_df.columns
            ],
            axis=1,
        )
    else:
        styled_df = filtered_df

    # 알림 목록 표 (보정상세는 표에서만 숨김)
    st.subheader("📋 알림 목록")
    st.dataframe(
        styled_df,
        hide_index=True,
        width="stretch",
    )

    st.markdown("---")
    # 알림 상세
    st.subheader("🔍 알림 상세")
    if not filtered_df.empty:
        alert_times = filtered_df["시간"].tolist()
        selected_time = st.selectbox(
            "알림 선택", options=alert_times, help="선택한 알림의 상세 내용을 확인합니다."
        )

        if selected_time:
            selected_row = df_alarms[df_alarms["시간"] == selected_time].iloc[0]
            is_corrected = bool(selected_row["보정내역"])
            border_color = "#66C87F" if is_corrected else "lightcoral"
            status_icon = "✅" if is_corrected else "⚠️"

            correction_detail = selected_row.get("보정상세", "")
            description = selected_row.get("설명", "설명 없음")

            st.markdown(
                f"""
                <div style="
                    border: 2px solid {border_color};
                    border-radius: 10px;
                    padding: 20px;
                    background-color: #f9f9f9;
                    margin-bottom: 20px;
                ">
                    <h3 style="margin-top: 0;">{status_icon} {selected_row['알림 유형']} 알림</h3>
                    <p><b>⏰ 발생 시간:</b> {selected_row['시간']}</p>
                    <p><b>⚠️ 상태:</b> {selected_row['상태']}</p>
                    <p><b>📝 상세 설명:</b> {description}</p>
                    <hr>
                    <p><b>🔧 보정 상태:</b> {selected_row['보정내역'] or '미보정'}</p>
                    <p><b>📊 보정 상세:</b><br>
                        <span style="font-size: 13px; color: #555;">
                            {correction_detail or '보정 상세 정보 없음'}
                        </span>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 수동 보정 버튼 (미보정일 때만)
            if not is_corrected:
                if st.button("✋ 이 알림 수동 보정 처리", key=f"manual_{selected_time}"):
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cs = f"수동 보정 ({now})"
                    cd = "사용자가 대시보드에서 수동 보정으로 처리했습니다."

                    # DB 업데이트
                    if update_alarm_correction(selected_time, cs, cd):
                        # 메모리상의 df_alarms도 갱신
                        idx = df_alarms[df_alarms["시간"] == selected_time].index[0]
                        df_alarms.at[idx, "보정내역"] = cs
                        df_alarms.at[idx, "보정상세"] = cd
                        st.session_state.alarm_data = df_alarms
                        st.success("수동 보정 상태로 변경되었습니다.")
                        st.rerun()
                    else:
                        st.error("수동 보정 상태 저장에 실패했습니다.")
    else:
        st.info("상세를 볼 알림이 없습니다.")

    # 보정된 센서 데이터 미리보기 (옵션)
    with st.expander("📊 보정된 센서 데이터 미리보기"):
        try:
            conn = sqlite3.connect(ALARMS_DB_PATH)
            q = """
                SELECT time_str, humidity, temperature, irradiance, source, created_at
                FROM corrected_sensor
                ORDER BY created_at DESC
                LIMIT 10
            """
            prev_df = pd.read_sql(q, conn)
            conn.close()
            if not prev_df.empty:
                st.dataframe(prev_df, width='stretch')
            else:
                st.caption("아직 보정된 센서 데이터가 없습니다.")
        except Exception as e:
            st.error(f"보정 데이터 로드 중 오류: {e}")


if __name__ == "__main__":
    show_alarms()
