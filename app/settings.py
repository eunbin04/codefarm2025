# settings.py
import streamlit as st
import json
import os
import pandas as pd

from app_details.utils import get_korea_time

SETTINGS_FILE = "config/settings.json"
STATION_CSV_PATH = "data/station_code.csv"  # 지역/지점 선택용


def _load_station_table():
    """지점 코드 CSV를 읽어 지역/지점 리스트를 준비합니다."""
    if not os.path.exists(STATION_CSV_PATH):
        return pd.DataFrame(columns=["지역", "지점명", "지점"])
    df = pd.read_csv(STATION_CSV_PATH)
    for col in ["지역", "지점명"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def save_settings_to_file():
    settings_data = {
        "farm_name": st.session_state.get("farm_name", "CODEFARM 온실"),
        "alert_enabled": st.session_state.get("alert_enabled", True),
        "daily_stat_time": st.session_state.get("daily_stat_time", "21:00"),
        "auto_train_time": st.session_state.get("auto_train_time", "00:00"),
        "t_location": st.session_state.get("t_location", 3),
        "h_location": st.session_state.get("h_location", 2),
        "r_location": st.session_state.get("r_location", 4),

        # === 추가: 시뮬레이션용 설정들 ===
        "region": st.session_state.get("region", None),
        "station_name": st.session_state.get("station_name", None),
        "station_id": st.session_state.get("station_id", None),

        "facility_key": st.session_state.get("facility_key", "glass_venlo"),
        "cover_type": st.session_state.get("cover_type", "film_PE"),

        "vent_angle_deg": st.session_state.get("vent_angle_deg", 30.0),
        "gh_height": st.session_state.get("gh_height", 4.5),
    }
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings_data, f, ensure_ascii=False, indent=4)


def load_settings_from_file():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        for key, val in settings.items():
            st.session_state[key] = val
    else:
        if "farm_name" not in st.session_state:
            st.session_state["farm_name"] = "CODEFARM 온실"
        if "alert_enabled" not in st.session_state:
            st.session_state["alert_enabled"] = True
        if "daily_stat_time" not in st.session_state:
            st.session_state["daily_stat_time"] = "21:00"
        if "auto_train_time" not in st.session_state:
            st.session_state["auto_train_time"] = "00:00"
        if "t_location" not in st.session_state:
            st.session_state["t_location"] = 3
        if "h_location" not in st.session_state:
            st.session_state["h_location"] = 2
        if "r_location" not in st.session_state:
            st.session_state["r_location"] = 4

        # 새로 추가된 것들 기본값
        st.session_state.setdefault("region", None)
        st.session_state.setdefault("station_name", None)
        st.session_state.setdefault("station_id", None)
        st.session_state.setdefault("facility_key", "glass_venlo")
        st.session_state.setdefault("cover_type", "film_PE")
        st.session_state.setdefault("vent_angle_deg", 30.0)
        st.session_state.setdefault("gh_height", 4.5)


def show_settings():
    st.title("⚙️ 설정")
    st.markdown("---")

    if st.session_state.get("loaded", False) is False:
        load_settings_from_file()
        st.session_state["loaded"] = True

    korea_now = get_korea_time()
    df_station = _load_station_table()

    with st.form("settings_form"):
        # ---------------- 기본 설정 ----------------
        st.markdown("##### 기본 설정")
        farm_name = st.text_input("농장명", value=st.session_state.get("farm_name", "CODEFARM 온실"))

        alert_options = {True: "🔔 활성화", False: "🔕 비활성화"}
        alert_enabled = st.selectbox(
            "경고 알림 설정",
            options=[True, False],
            format_func=lambda x: alert_options[x],
            index=0 if st.session_state.get("alert_enabled", True) else 1,
            help="데이터에 이상이 있을 때 알림을 받습니다.",
        )

        st.markdown("---")
        st.markdown("##### 🕒 하루 통계 수신 시각 설정")
        hours = [f"{i:02d}" for i in range(24)]
        minutes = [f"{i:02d}" for i in range(60)]

        if "daily_stat_time" in st.session_state:
            h, m = st.session_state["daily_stat_time"].split(":")
        else:
            h = f"{korea_now.hour:02d}"
            m = f"{korea_now.minute:02d}"

        col1, col2 = st.columns([1, 1])
        with col1:
            selected_hour = st.selectbox("시", options=hours, index=hours.index(h))
        with col2:
            selected_minute = st.selectbox(
                "분",
                options=minutes,
                index=minutes.index(m),
                help="24시간 동안의 데이터 통계량을 분석해 알립니다.",
            )
        daily_stat_time = f"{selected_hour}:{selected_minute}"

        st.markdown("---")
        st.markdown("##### ⌛ 자동 모델 학습 시각 설정")
        if "auto_train_time" in st.session_state:
            ath, atm = st.session_state["auto_train_time"].split(":")
        else:
            ath = "02"
            atm = "00"
        c1, c2 = st.columns([1, 1])
        with c1:
            auto_train_hour = st.selectbox("시", options=hours, index=hours.index(ath), key="auto_train_hour")
        with c2:
            auto_train_minute = st.selectbox(
                "분",
                options=minutes,
                index=minutes.index(atm),
                key="auto_train_minute",
                help="데이터 학습 모델의 학습 주기를 설정합니다.",
            )
        auto_train_time = f"{auto_train_hour}:{auto_train_minute}"

        # ---------------- 데이터 인덱스 ----------------
        st.markdown("---")
        st.markdown("##### 🎯 데이터 인덱스 설정")
        st.markdown("컬럼 인덱스는 **0부터 시작**합니다. CSV/엑셀 파일 열 번호를 참고하세요.")
        t_location = st.number_input(
            "온도 인덱스", min_value=0, value=int(st.session_state.get("t_location", 3))
        )
        h_location = st.number_input(
            "습도 인덱스", min_value=0, value=int(st.session_state.get("h_location", 2))
        )
        r_location = st.number_input(
            "광 인덱스", min_value=0, value=int(st.session_state.get("r_location", 4))
        )

        # ---------------- 지역/지점 선택 ----------------
        st.markdown("---")
        st.markdown("##### ⛅ 기상 관측 지점 선택 (지역/지점)")

        if df_station.empty:
            st.warning("data/station_code.csv 를 찾을 수 없습니다. 지점 선택 기능이 비활성화됩니다.")
            region = None
            station_name = None
            station_id = None
        else:
            regions = sorted(df_station["지역"].dropna().unique())

            # 1) 지역 기본값 결정
            saved_region = st.session_state.get("region")
            if saved_region in regions:
                default_region = saved_region
            else:
                default_region = regions[0] if regions else None

            region = st.selectbox("지역 선택", options=regions,
                                index=regions.index(default_region))

            # 2) 선택된 지역에 해당하는 지점만 필터
            df_region = df_station[df_station["지역"] == region]
            station_names = df_region["지점명"].tolist()

            # 3) 지점 기본값: 이전에 저장된 station_name이 현재 지역에 있을 때만 유지
            saved_station_name = st.session_state.get("station_name")
            if saved_station_name in station_names:
                default_station_name = saved_station_name
            else:
                default_station_name = station_names[0] if station_names else None

            station_name = st.selectbox(
                "지점 선택",
                options=station_names,
                index=station_names.index(default_station_name) if default_station_name else 0,
            )

            # 4) 선택된 지점의 코드 가져오기
            stn_row = df_region[df_region["지점명"] == station_name].iloc[0]
            station_id = int(stn_row["지점"])

            st.caption(f"선택된 지점코드: {station_id}")

        # ---------------- 시설/피복 선택 ----------------
        st.markdown("---")
        st.markdown("##### 🏡 시설 유형 및 피복 선택")

        facility_display = {
            "glass_span": "유리온실(양지붕형)",
            "glass_venlo": "유리온실(벤로형)",
            "rigid_house": "경질온실",
        }
        facility_keys = list(facility_display.keys())
        current_fac = st.session_state.get("facility_key", "glass_venlo")
        if current_fac not in facility_keys:
            current_fac = "glass_venlo"

        fac = st.selectbox(
            "시설 유형",
            options=facility_keys,
            format_func=lambda k: facility_display.get(k, k),
            index=facility_keys.index(current_fac),
        )

        cover_options = {
            "film_PE": "PE",
            "film_PVC": "PVC",
            "film_EVA": "EVA",
            "film_PO": "PO",
            "film_woven": "직조필름",
        }
        cover_keys = list(cover_options.keys())
        current_cover = st.session_state.get("cover_type", "film_PE")
        if current_cover not in cover_keys:
            current_cover = "film_PE"

        cover = st.selectbox(
            "피복 자재",
            options=cover_keys,
            format_func=lambda k: cover_options.get(k, k),
            index=cover_keys.index(current_cover),
            help="현재 시설에서 사용하는 피복 재질을 선택하세요.",
        )

        # ---------------- 온실 조건 (환기각, 층고) ----------------
        st.markdown("---")
        st.markdown("##### 🍃 온실 조건 설정")

        vent_angle_deg = st.number_input(
            "환기창 개도각 (도)", min_value=0.0, max_value=45.0,
            value=float(st.session_state.get("vent_angle_deg", 30.0)),
            step=1.0,
            help="천창/측창의 개도각을 설정합니다. (0~45도)",
        )

        gh_height = st.number_input(
            "온실 층고(높이, m)", min_value=1.0,
            value=float(st.session_state.get("gh_height", 4.5)),
            step=0.1,
            help="온실 평균 층고를 입력하세요.",
        )

        submitted = st.form_submit_button("저장")

        if submitted:
            st.session_state["farm_name"] = farm_name
            st.session_state["alert_enabled"] = alert_enabled
            st.session_state["daily_stat_time"] = daily_stat_time
            st.session_state["auto_train_time"] = auto_train_time
            st.session_state["t_location"] = int(t_location)
            st.session_state["h_location"] = int(h_location)
            st.session_state["r_location"] = int(r_location)

            st.session_state["region"] = region
            st.session_state["station_name"] = station_name
            st.session_state["station_id"] = station_id

            st.session_state["facility_key"] = fac
            st.session_state["cover_type"] = cover

            st.session_state["vent_angle_deg"] = float(vent_angle_deg)
            st.session_state["gh_height"] = float(gh_height)

            save_settings_to_file()
            st.success("설정이 저장되었습니다!")
