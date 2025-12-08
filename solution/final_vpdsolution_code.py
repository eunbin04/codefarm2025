#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vpd_final_per_area.py

이 스크립트는 기존 vpd 모델을 리팩토링하여 **단위 면적당(per m²)** 기반으로 온실의
열수지와 VPD 제어를 시뮬레이션합니다. 온실의 총 면적을 알 필요 없이,
사용자로부터 **온실 층고(높이)** 만 입력받아 모델에 이용합니다. 이를 통해
온실 규모에 무관하게 동일한 코드로 평가가 가능합니다.

변경된 주요 사항:

* 열수지 계산을 단위 면적 기준으로 수행하기 위해 `gh_floor_area`를 항상 1.0으로 설정합니다.
* 전도 손실은 외피 면적과 바닥면적의 비율(약 1.6)을 그대로 사용하여 per m² 손실을 계산합니다.
* 환기 손실 및 열용량은 단위 면적당 온실 체적을 사용하여 계산합니다. 이때 층고(높이)를
  사용자에게 입력받아 `gh_height`로 사용합니다.
* VPD 제어 함수(`suggest_low_energy_vpd_control`)도 기본 면적을 1.0 m²로 가정하여
  계산됩니다. 층고에 따라 온실 체적과 공기량을 계산합니다.

사용법:

1. 코드 실행 시 `main()` 함수를 호출하면, 사용자로부터 환기창 개도각과 온실 층고를
   입력받습니다. 이후 모델을 실행하여 결과를 CSV로 저장하고, VPD 제어 솔루션을
   계산합니다.
2. 온실 층고 입력은 반드시 양수여야 합니다. 올바르지 않은 입력이 들어오면 기본값
   4.0 m로 대체됩니다.

NOTE: 이 파일은 Jupyter/Colab 등의 환경에서 직접 실행할 수 있습니다.
"""

import pandas as pd
import numpy as np
import requests

# ---------------- 기본 설정 ----------------
STATION_DIR = "/content/drive/MyDrive/final_project/지점코드.csv"
GROWTH_CSV_PATH = "/content/drive/MyDrive/final_project/9_11월_미기후.csv"

ASOS_URL = "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"

# lux -> W/m2 환산 상수
LUX_TO_WM2 = 0.0083


# ============================================================
# 1. 지점(관측소) 선택 관련 함수
# ============================================================
def load_station_table(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    if "지역" not in df.columns:
        df["지역"] = ""

    for col in ["지역", "지점명"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def choose_region(df: pd.DataFrame) -> str:
    regions = sorted(df["지역"].dropna().unique())
    if not regions:
        raise ValueError("CSV에 '지역' 값이 없습니다. '지역' 열을 확인해주세요.")

    print("\n=== 지역 선택 ===")
    for i, r in enumerate(regions, start=1):
        print(f"{i}. {r}")

    while True:
        try:
            idx = int(input("번호를 선택하세요: ").strip())
            if 1 <= idx <= len(regions):
                region = regions[idx - 1]
                return region
        except ValueError:
            pass
        print("잘못된 입력입니다. 다시 입력해 주세요.")


def choose_station(df_region: pd.DataFrame):
    df_sorted = df_region.sort_values("지점명").reset_index(drop=True)

    print("\n=== 지점(관측소) 선택 ===")
    for i, row in df_sorted.iterrows():
        print(f"{i+1}. {row['지점명']} (지점코드: {row['지점']})")

    while True:
        try:
            idx = int(input("번호를 선택하세요: ").strip())
            if 1 <= idx <= len(df_sorted):
                row = df_sorted.iloc[idx - 1]
                stn_name = row["지점명"]
                stn_code = int(row["지점"])  # 숫자 코드
                return stn_name, stn_code
        except ValueError:
            pass
        print("잘못된 입력입니다. 다시 입력해 주세요.")


def select_station_interactive() -> str:
    """
    CSV에서 지역/지점을 선택해서 최종 STN_ID 문자열을 리턴
    """
    csv_path = STATION_DIR
    df = load_station_table(csv_path)

    region = choose_region(df)
    df_region = df[df["지역"] == region]
    print(f"\n[선택된 지역] {region} (지점 수: {len(df_region)})")

    stn_name, stn_code = choose_station(df_region)

    STN_ID = str(stn_code)

    print("\n=== 최종 선택 결과 ===")
    print(f"지역: {region}")
    print(f"지점명: {stn_name}")
    print(f"지점코드: {stn_code}")
    print(f'STN_ID = "{STN_ID}"')

    return STN_ID


# ============================================================
# 2. 온실 10분 평균 만들기
# ============================================================
def make_greenhouse_10min(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)

    # "2025-09-01 T 00:01" → datetime
    df["datetime"] = pd.to_datetime(
        df["date_time"].str.replace(" T ", " "),
        errors="coerce"
    )

    df = df.set_index("datetime").sort_index()

    # 숫자형 컬럼만 10분 평균
    num_cols = df.select_dtypes(include=[np.number]).columns
    df_10min = df[num_cols].resample("10min").mean()

    # light → lux / Wm2
    if "light" in df_10min.columns:
        df_10min["light_lux"] = df_10min["light"]
        df_10min["light_Wm2"] = df_10min["light"] * LUX_TO_WM2

    df_10min = df_10min.reset_index()
    return df_10min


# ============================================================
# 3. ASOS API 호출 + 10분 보간
# ============================================================
def fetch_asos_hourly(stn_id: str,
                      start_dt: pd.Timestamp,
                      end_dt: pd.Timestamp,
                      service_key: str,
                      max_requests: int = 5) -> pd.DataFrame:

    all_items = []
    current_start_dt = start_dt
    request_count = 0

    while current_start_dt <= end_dt:
        if max_requests is not None and request_count >= max_requests:
            print(f"[ASOS] max_requests={max_requests}에 도달, 여기까지 데이터만 가져옵니다.")
            break

        start_date_str = current_start_dt.strftime("%Y%m%d")
        current_end_dt = min(current_start_dt + pd.Timedelta(days=30), end_dt)
        end_date_str = current_end_dt.strftime("%Y%m%d")

        params = {
            "serviceKey": service_key,
            "dataType": "JSON",
            "dataCd": "ASOS",
            "dateCd": "HR",
            "startDt": start_date_str,
            "startHh": "00",
            "endDt": end_date_str,
            "endHh": "23",
            "stnIds": stn_id,
            "pageNo": "1",
            "numOfRows": "999",
        }

        headers = {"User-Agent": "Mozilla/5.0"}

        resp = requests.get(ASOS_URL, params=params, headers=headers)
        print(f"[ASOS] Request for {start_date_str} to {end_date_str} status: {resp.status_code}")
        print("[ASOS] URL:", resp.url)

        request_count += 1

        if resp.status_code != 200:
            print("[ASOS] 에러 응답:")
            print(resp.text[:500])
            current_start_dt = current_end_dt + pd.Timedelta(days=1)
            continue

        try:
            data = resp.json()
            body = data.get('response', {}).get('body', {})
            items_obj = body.get('items')
            if items_obj is None:
                print("[ASOS] items 가 없습니다. 구조 확인 필요.")
                items = []
            else:
                items = items_obj.get('item', [])
            all_items.extend(items)
        except Exception as e:
            print(f"[ASOS] JSON 파싱 오류: {e}")
            print(resp.text[:500])

        current_start_dt = current_end_dt + pd.Timedelta(days=1)

    rows = []
    for it in all_items:
        rows.append({
            "datetime": it.get("tm"),
            "ext_temp": it.get("ta"),
            "ext_rh": it.get("hm"),
            "ext_icsr_MJ": it.get("icsr"),
            "ext_wind_ms": it.get("ws"),
        })

    df_hourly = pd.DataFrame(rows)

    if df_hourly.empty:
        print("[ASOS] 조회된 시간별 데이터가 없습니다.")
        return pd.DataFrame(columns=["datetime", "ext_temp", "ext_rh", "ext_icsr_MJ", "ext_icsr_Wm2", "ext_wind_ms"])

    df_hourly["datetime"] = pd.to_datetime(
        df_hourly["datetime"],
        format="%Y-%m-%d %H:%M",
        errors="coerce"
    )
    df_hourly["ext_temp"] = pd.to_numeric(df_hourly["ext_temp"], errors="coerce")
    df_hourly["ext_rh"] = pd.to_numeric(df_hourly["ext_rh"], errors="coerce")
    df_hourly["ext_icsr_MJ"] = pd.to_numeric(df_hourly["ext_icsr_MJ"], errors="coerce").fillna(0.0)
    df_hourly["ext_wind_ms"] = pd.to_numeric(df_hourly["ext_wind_ms"], errors="coerce")

    df_hourly["ext_icsr_Wm2"] = df_hourly["ext_icsr_MJ"] * (1_000_000 / 3600.0)
    df_hourly = df_hourly.sort_values("datetime")

    return df_hourly


def make_asos_10min(df_hourly: pd.DataFrame,
                    start_dt: pd.Timestamp,
                    end_dt: pd.Timestamp) -> pd.DataFrame:

    if df_hourly.empty:
        print("[ASOS] 시간자료 DF가 비어있음")
        return pd.DataFrame(columns=["datetime", "ext_temp", "ext_rh", "ext_icsr_MJ", "ext_icsr_Wm2", "ext_wind_ms"])

    df_hourly = df_hourly.set_index("datetime").sort_index()

    start_10 = start_dt.floor("10min")
    end_10 = end_dt.ceil("10min")
    idx_10min = pd.date_range(start_10, end_10, freq="10min")

    if len(df_hourly) < 2:
        print("[ASOS] 보간을 위한 데이터 포인트가 부족합니다. 최소 2개 필요.")
        return pd.DataFrame(columns=["datetime", "ext_temp", "ext_rh", "ext_icsr_MJ", "ext_icsr_Wm2", "ext_wind_ms"])

    df_10min_ext = df_hourly.reindex(idx_10min).interpolate(method="time")
    df_10min_ext = df_10min_ext.reset_index().rename(columns={"index": "datetime"})
    return df_10min_ext


# ============================================================
# 4. 온실 + ASOS 병합
# ============================================================
def merge_greenhouse_asos(df_gh10: pd.DataFrame,
                          df_asos10: pd.DataFrame) -> pd.DataFrame:
    df_gh = df_gh10.set_index("datetime").sort_index()
    df_as = df_asos10.set_index("datetime").sort_index()
    df_merged = df_gh.join(df_as, how="left")
    df_merged = df_merged.reset_index()
    return df_merged


# ============================================================
# 5. 시설 유형 / 피복 메뉴
# ============================================================
FACILITY_TYPES = {
    "1": {
        "facility_key": "glass_span",
        "name_kr": "유리온실(양지붕형)",
        "cover_options": {
            "1": {"cover_type": "film_PE",    "name_kr": "PE"},
            "2": {"cover_type": "film_PVC",   "name_kr": "PVC"},
            "3": {"cover_type": "film_EVA",   "name_kr": "EVA"},
            "4": {"cover_type": "film_PO",    "name_kr": "PO"},
            "5": {"cover_type": "film_woven", "name_kr": "직조필름"},
        },
    },
    "2": {
        "facility_key": "glass_venlo",
        "name_kr": "유리온실(벤로형)",
        "cover_options": {
            "1": {"cover_type": "film_PE",    "name_kr": "PE"},
            "2": {"cover_type": "film_PVC",   "name_kr": "PVC"},
            "3": {"cover_type": "film_EVA",   "name_kr": "EVA"},
            "4": {"cover_type": "film_PO",    "name_kr": "PO"},
            "5": {"cover_type": "film_woven", "name_kr": "직조필름"},
        },
    },
    "3": {
        "facility_key": "rigid_house",
        "name_kr": "경질온실",
        "cover_options": {
            "1": {
                "cover_type": "panel_fluoro",
                "name_kr": "불소수지 sheets (PMMA / ETFE / PVDF 계열)",
            },
            "2": {
                "cover_type": "panel_PET1",
                "name_kr": "PET sheets",
            },
            "3": {
                "cover_type": "panel_PC",
                "name_kr": "PC판",
            },
            "4": {
                "cover_type": "panel_PET2",
                "name_kr": "PET판",
            },
        },
    },
}

# 시설별 골조율(광이 통과하는 비율) – 값은 예시, 나중에 실제 설계 값으로 수정 가능
FACILITY_FRAME_RATIO = {
    "glass_span": 0.80,   # 유리온실(양지붕형) : 골조 등으로 20% 차폐 → 80% 통과
    "glass_venlo": 0.88,  # 유리온실(벤로형)   : 12% 차폐 → 88% 통과 (예시)
    "rigid_house": 0.85,  # 경질온실          : 15% 차폐 → 85% 통과
}


def choose_facility_and_cover() -> tuple[str, str]:
    # 시설 유형 선택
    print("=== 시설 유형을 선택하세요 ===")
    for num, info in FACILITY_TYPES.items():
        print(f"{num}. {info['name_kr']}")

    while True:
        fac_choice = input("시설 유형 번호 입력: ").strip()
        if fac_choice in FACILITY_TYPES:
            break
        print("잘못 입력했습니다. 1~3 중에서 다시 입력하세요.")

    fac_info = FACILITY_TYPES[fac_choice]
    facility_key = fac_info["facility_key"]

    # 피복 선택
    print(f"\n[{fac_info['name_kr']}] 을(를) 선택했습니다.")
    print("=== 피복 자재를 선택하세요 ===")
    for num, opt in fac_info["cover_options"].items():
        print(f"{num}. {opt['name_kr']}")

    while True:
        cov_choice = input("피복 자재 번호 입력: ").strip()
        if cov_choice in fac_info["cover_options"]:
            break
        print("잘못 입력했습니다. 메뉴에 있는 번호로 다시 입력하세요.")

    cover_info = fac_info["cover_options"][cov_choice]
    cover_type = cover_info["cover_type"]

    print(f"\n→ 선택 결과: 시설 = {fac_info['name_kr']}, 피복 = {cover_info['name_kr']}")
    print(f"   (내부적으로 cover_type = '{cover_type}')\n")

    return facility_key, cover_type


# 피복/스크린 물성
COVER_MATERIALS = {
    "glass_single": {
        "name_kr": "단층 유리",
        "tau": 0.91,
        "U": 6.0,   # W/m2K (예시)
    },
    "film_PE": {
        "name_kr": "PE 필름",
        "tau": 0.65,
        "U": 7.0,   # 단층 필름은 보통 유리보다 조금 더 큼 (예시)
    },
    "film_EVA": {
        "name_kr": "EVA 필름",
        "tau": 0.88,
        "U": 6.5,
    },
    "film_PO": {
        "name_kr": "PO 필름",
        "tau": 0.88,
        "U": 6.5,
    },
    "film_PVC": {
        "name_kr": "PVC 필름",
        "tau": 0.80,
        "U": 6.5,
    },
    "film_woven": {
        "name_kr": "직조필름",
        "tau": 0.55,
        "U": 6.0,
    },
    "panel_fluoro": {
        "name_kr": "불소수지 패널",
        "tau": 0.80,
        "U": 4.0,
    },
    "panel_PET1": {
        "name_kr": "PET 패널",
        "tau": 0.78,
        "U": 4.0,
    },
    "panel_PET2": {
        "name_kr": "PET 패널",
        "tau": 0.78,
        "U": 4.0,
    },
    "panel_PC": {
        "name_kr": "PC 패널",
        "tau": 0.80,
        "U": 3.5,
    },
}

SCREEN_MATERIALS = {
    "none": {
        "name_kr": "차광 없음",
        "shading_rate": 0.0,
        "u_factor": 1.0,
    },
    "screen_35": {
        "name_kr": "차광 35%",
        "shading_rate": 0.35,
        "u_factor": 0.85,
    },
    "screen_50": {
        "name_kr": "차광 50%",
        "shading_rate": 0.50,
        "u_factor": 0.80,
    },
    "screen_70": {
        "name_kr": "차광 70%",
        "shading_rate": 0.70,
        "u_factor": 0.75,
    },
}


def add_inside_radiation_model(
    df: pd.DataFrame,
    facility_key: str,                # 시설 유형 (glass_span, glass_venlo, rigid_house)
    cover_type: str,
    screen_type: str,
    k_internal: float = 0.8,          # 구조물/작물 등 추가 감쇠 계수 (대략 0.7~0.9)
    ext_col: str = "ext_icsr_Wm2",
    prefix: str = "rad_model_",       # 컬럼 이름 prefix
) -> pd.DataFrame:
    """
    외부 일사(ext_icsr_Wm2)와 피복/스크린/골조율 정보를 이용해서
    온실 내부로 들어오는 광량(W/m2, lux)을 계산하는 함수.

    생성되는 컬럼:
      - rad_model_noshade_Wm2
      - rad_model_shaded_Wm2
      - rad_model_noshade_lux
      - rad_model_shaded_lux
    """

    if cover_type not in COVER_MATERIALS:
        raise ValueError(f"알 수 없는 cover_type: {cover_type}")
    if screen_type not in SCREEN_MATERIALS:
        raise ValueError(f"알 수 없는 screen_type: {screen_type}")
    if ext_col not in df.columns:
        raise KeyError(f"'{ext_col}' 컬럼이 없습니다. ASOS 10분 자료가 제대로 병합됐는지 확인하세요.")

    if facility_key not in FACILITY_FRAME_RATIO:
        raise ValueError(f"알 수 없는 facility_key: {facility_key} (FACILITY_FRAME_RATIO를 확인하세요.)")

    tau_cover = COVER_MATERIALS[cover_type]["tau"]
    shading_rate = SCREEN_MATERIALS[screen_type]["shading_rate"]
    frame_ratio = FACILITY_FRAME_RATIO[facility_key]   # 시설별 골조율

    # 외부 일사 (W/m2)
    G_ext = pd.to_numeric(df[ext_col], errors="coerce").fillna(0.0)

    # 피복 + 골조까지 통과했을 때 내부 일사 (무차광, 작물/배드 감쇠 포함)
    G_in_noshade = G_ext * tau_cover * frame_ratio * k_internal

    # 차광스크린까지 고려한 내부 일사
    G_in_shaded = G_ext * tau_cover * (1.0 - shading_rate) * frame_ratio * k_internal

    df[f"{prefix}noshade_Wm2"] = G_in_noshade
    df[f"{prefix}shaded_Wm2"] = G_in_shaded

    # lux로 환산
    df[f"{prefix}noshade_lux"] = G_in_noshade / LUX_TO_WM2
    df[f"{prefix}shaded_lux"] = G_in_shaded / LUX_TO_WM2

    return df


# ============================================================
# 6. VPD/수증기 관련 함수
# ============================================================
def saturation_vapor_pressure_kPa(T_C):
    """포화 수증기압(kPa), T_C: °C"""
    if isinstance(T_C, (pd.Series, pd.Index)):
        T = T_C.astype(float)
    else:
        T = pd.Series([T_C], dtype=float)
    es = 0.6108 * np.exp(17.27 * T / (T + 237.3))
    return es if isinstance(T_C, (pd.Series, pd.Index)) else es.iloc[0]


def calc_vpd_kPa(T_C, RH):
    """
    T_C, RH 둘 다 Series여도 되고, float(스칼라)여도 됨.
    - 둘 다 Series면 Series VPD 반환
    - 둘 다 float이면 float VPD 반환
    """
    es = saturation_vapor_pressure_kPa(T_C)

    if isinstance(RH, (pd.Series, pd.Index)):
        rh_frac = RH.astype(float) / 100.0
    else:
        rh_frac = float(RH) / 100.0  # 스칼라 처리

    ea = es * rh_frac
    vpd = es - ea
    return vpd


def recalc_rh_const_abs_humidity(T_old_C: pd.Series,
                                 RH_old: pd.Series,
                                 T_new_C: pd.Series) -> pd.Series:
    """절대습도 일정 가정하고 온도만 바뀔 때 새로운 RH 계산"""
    es_old = saturation_vapor_pressure_kPa(T_old_C)
    es_new = saturation_vapor_pressure_kPa(T_new_C)
    ea_old = es_old * (RH_old.astype(float) / 100.0)
    RH_new = (ea_old / es_new) * 100.0
    return RH_new.clip(lower=0.0, upper=100.0)


# ============================================================
# 6-1. 광·온도 기반 VPD 목표 추천 (Stanghellini + VPD 차트 참고)
# ============================================================
def recommend_vpd_target(T_now, I_inside_Wm2=None):
    """
    T_now(°C)와 온실 내 일사(W/m2)를 이용해서
    권장 VPD 목표(kPa)를 간단히 추천하는 함수.

    - Stanghellini(1992)와 일반 VPD chart를 참고해서
      광이 높을수록 VPD를 조금 더 높게 허용하도록 설계.
    """
    ppfd = None
    if I_inside_Wm2 is not None and not np.isnan(I_inside_Wm2):
        # 매우 대략적인 환산: 1 W/m2 ≈ 2 µmol/m2/s
        ppfd = I_inside_Wm2 * 2.0

    # 1) 광정보가 있으면 PPFD 기준으로
    if ppfd is not None:
        if ppfd < 200:
            return 0.7   # 저광기 : 0.6~0.8
        elif ppfd < 400:
            return 0.9   # 중저광 : 0.8~1.0
        elif ppfd < 600:
            return 1.1   # 중광   : 1.0~1.2
        elif ppfd < 800:
            return 1.3   # 고광   : 1.2~1.4
        else:
            return 1.5   # 아주 고광 : 1.4~1.6

    # 2) 광정보 없으면 온도만 보고 대략 설정
    if T_now < 18:
        return 0.7
    elif T_now < 22:
        return 0.9
    elif T_now < 26:
        return 1.1
    elif T_now < 30:
        return 1.3
    else:
        return 1.5


# ============================================================
# 7. 환기량(ACH) + 동적 열 수지 + 차광 모델
# ============================================================
def compute_ACH_series(df: pd.DataFrame,
                       base_ACH: float = 2.0,
                       max_extra_ACH: float = 30.0,
                       vent_angle_col: str = "vent_angle_deg",
                       wind_col: str = "ext_wind_ms",
                       use_dynamic: bool = True) -> pd.Series:
    """
    개도각 + 외기 풍속에 따라 환기회수(ACH)를 동적으로 계산
    """
    ach = pd.Series(base_ACH, index=df.index, dtype=float)
    if not use_dynamic:
        return ach

    if vent_angle_col in df.columns and wind_col in df.columns:
        vent = df[vent_angle_col].astype(float).clip(lower=0.0)
        wind = df[wind_col].astype(float).clip(lower=0.0)

        vent_factor = (vent / 90.0).clip(0.0, 1.0)
        wind_factor = (wind / 7.0).clip(0.0, 1.0)

        ach = base_ACH + max_extra_ACH * vent_factor * wind_factor
        return ach

    return ach


def estimate_inside_temp_with_shading(
    df_merged: pd.DataFrame,
    cover_type: str,
    screen_type: str,
    gh_floor_area: float,
    gh_height: float,
    U: float | None = None,     # ★ None이면 피복별 기본 U 사용
    ACH_base: float = 2.0,
    use_dynamic_ACH: bool = True,
    C_factor: float = 3.0,
    frac_solar_to_air: float = 0.4,
    time_col: str = "datetime",
    vent_angle_col: str = "vent_angle_deg",
    wind_col: str = "ext_wind_ms",
    default_dt_seconds: float = 600.0,
) -> pd.DataFrame:
    """
    외기기온/일사/환기/차광에 따른 실내 온도(차광/무차광) 시뮬레이션.
    피복별 U값 + 스크린별 u_factor를 반영해서 G_env를 계산한다.

    **단위 면적(per m²)** 모델이므로 `gh_floor_area`를 1.0으로 주고,
    `gh_height`는 사용자 입력 층고 값(m)이다. 체적은 1 m²에 대해 `gh_height`로
    계산된다.
    """
    df = df_merged.copy()

    # ---- 피복/스크린 체크 ----
    if cover_type not in COVER_MATERIALS:
        raise ValueError(f"알 수 없는 cover_type: {cover_type}")
    if screen_type not in SCREEN_MATERIALS:
        raise ValueError(f"알 수 없는 screen_type: {screen_type}")

    tau_cover = COVER_MATERIALS[cover_type]["tau"]
    shading_rate = SCREEN_MATERIALS[screen_type]["shading_rate"]
    u_factor_screen = SCREEN_MATERIALS[screen_type]["u_factor"]

    # ---- 피복별 U값 결정 (테이블 + 필요시 override) ----
    # U 인자를 None으로 두면 COVER_MATERIALS의 U값 사용
    if U is None:
        U_cover = COVER_MATERIALS[cover_type].get("U", 6.0)  # 기본값 6.0
    else:
        U_cover = float(U)

    # 단위 면적 모델: gh_floor_area는 1.0으로 주어지며, gh_height는 사용자 입력
    gh_volume = gh_floor_area * gh_height
    gh_envelope_area = gh_floor_area * 1.6  # 대략적인 외피 면적 (per m²)

    rho_air = 1.2
    cp_air = 1000.0  # J/kgK

    # ---- 전도(외피) 열손실 계수 (피복 + 스크린 반영) ----
    G_env_noshade = U_cover * gh_envelope_area
    # 스크린이 있으면 u_factor_screen < 1 → 열손실 줄어듦
    G_env_shaded = U_cover * u_factor_screen * gh_envelope_area

    # ---- 환기에 의한 열손실 계수 ----
    ach_series = compute_ACH_series(
        df,
        base_ACH=ACH_base,
        max_extra_ACH=30.0,
        vent_angle_col=vent_angle_col,
        wind_col=wind_col,
        use_dynamic=use_dynamic_ACH,
    )
    # 환기 손실 per m²: ρ * cp * h * ACH / 3600
    G_vent_series = rho_air * cp_air * (gh_height * ach_series / 3600.0)

    df["ACH"] = ach_series
    df["U_cover"] = U_cover              # 디버깅/분석용
    df["U_screen_factor"] = u_factor_screen
    df["G_env_noshade"] = G_env_noshade
    df["G_env_shaded"] = G_env_shaded
    df["G_vent"] = G_vent_series
    df["G_loss_noshade"] = G_env_noshade + G_vent_series
    df["G_loss_shaded"] = G_env_shaded + G_vent_series

    # ---- 일사/외기 ----
    G_ext = df.get("ext_icsr_Wm2", pd.Series(0.0, index=df.index)).fillna(0.0).astype(float)
    T_out = df.get("ext_temp", pd.Series(np.nan, index=df.index)).astype(float)

    # 커버 통과 일사 per m²
    Q_solar_noshade = G_ext * gh_floor_area * tau_cover
    Q_solar_shaded = G_ext * gh_floor_area * tau_cover * (1.0 - shading_rate)

    # 일사 중 공기로 바로 전달되는 비율
    Q_air_noshade = Q_solar_noshade * frac_solar_to_air
    Q_air_shaded = Q_solar_shaded * frac_solar_to_air

    df["Q_solar_noshade"] = Q_solar_noshade
    df["Q_solar_shaded"] = Q_solar_shaded
    df["Q_air_noshade"] = Q_air_noshade
    df["Q_air_shaded"] = Q_air_shaded

    # ---- 시간 간격 dt 계산 ----
    if time_col in df.columns:
        times = pd.to_datetime(df[time_col])
    elif isinstance(df.index, pd.DatetimeIndex):
        times = df.index
    else:
        times = pd.date_range("2000-01-01", periods=len(df), freq=f"{int(default_dt_seconds)}S")

    df["_time_for_dt"] = times
    dt_seconds = df["_time_for_dt"].diff().dt.total_seconds().fillna(default_dt_seconds)
    dt_seconds = dt_seconds.clip(lower=1.0)

    # ---- 열용량 (공기 + 구조물 계수) ----
    C_air = rho_air * cp_air * gh_volume
    C_eff = C_factor * C_air

    n = len(df)
    T_in_noshade = np.zeros(n, dtype=float)
    T_in_shaded = np.zeros(n, dtype=float)

    # 초기값: 실측 온도 있으면 그걸 쓰고, 없으면 외기 온도
    if "temperature" in df.columns and not df["temperature"].isna().all():
        T_init = float(df["temperature"].iloc[0])
    else:
        T_init = float(T_out.iloc[0]) if not np.isnan(T_out.iloc[0]) else 20.0

    T_in_noshade[0] = T_init
    T_in_shaded[0] = T_init

    # ---- Forward Euler 적분 ----
    for i in range(1, n):
        dt = dt_seconds.iloc[i]
        T_out_i = T_out.iloc[i]
        G_loss_n_i = df["G_loss_noshade"].iloc[i]
        G_loss_s_i = df["G_loss_shaded"].iloc[i]
        Qn_i = Q_air_noshade.iloc[i]
        Qs_i = Q_air_shaded.iloc[i]

        dTdt_n = (Qn_i - G_loss_n_i * (T_in_noshade[i - 1] - T_out_i)) / C_eff
        dTdt_s = (Qs_i - G_loss_s_i * (T_in_shaded[i - 1] - T_out_i)) / C_eff

        T_in_noshade[i] = T_in_noshade[i - 1] + dTdt_n * dt
        T_in_shaded[i] = T_in_shaded[i - 1] + dTdt_s * dt

    df["T_in_model_noshade"] = T_in_noshade
    df["T_in_model_shaded"] = T_in_shaded
    df["deltaT_screen"] = df["T_in_model_noshade"] - df["T_in_model_shaded"]

    # 열손실 항목별 비율
    df["share_env_loss_noshade"] = G_env_noshade / df["G_loss_noshade"]
    df["share_vent_loss_noshade"] = df["G_vent"] / df["G_loss_noshade"]
    df["share_env_loss_shaded"] = G_env_shaded / df["G_loss_shaded"]
    df["share_vent_loss_shaded"] = df["G_vent"] / df["G_loss_shaded"]

    # 모델 vs 실측 온도 오차
    if "temperature" in df.columns:
        df["T_measured"] = df["temperature"].astype(float)
        df["error_measured_vs_model_shaded"] = df["T_measured"] - df["T_in_model_shaded"]

    return df


def add_vpd_for_shading(df_with_shading: pd.DataFrame) -> pd.DataFrame:
    """
    차광 모델 결과에 VPD 관련 컬럼 추가
    """
    df = df_with_shading.copy()

    for col in ["temperature", "humidity", "T_in_model_shaded"]:
        if col not in df.columns:
            raise KeyError(f"'{col}' 컬럼이 없습니다.")

    T_meas = df["temperature"].astype(float)
    RH_meas = df["humidity"].astype(float)

    # 실측 VPD
    df["vpd_measured"] = calc_vpd_kPa(T_meas, RH_meas)

    # 모델 온도에서의 RH / VPD
    T_shaded = df["T_in_model_shaded"].astype(float)
    df["RH_model_shaded"] = recalc_rh_const_abs_humidity(
        T_old_C=T_meas,
        RH_old=RH_meas,
        T_new_C=T_shaded,
    )

    df["vpd_model_shaded"] = calc_vpd_kPa(
        T_C=T_shaded,
        RH=df["RH_model_shaded"],
    )

    df["deltaVPD_shading"] = df["vpd_measured"] - df["vpd_model_shaded"]

    return df


# ============================================================
# 8. VPD 에너지 최소 제어 솔루션
# ============================================================
def suggest_low_energy_vpd_control(
    T_now: float,
    RH_now: float,
    VPD_target=None,          # None이면 recommend_vpd_target()에서 자동 결정
    floor_area_m2: float = 1.0,
    height_m: float = 4.0,
    T_cool_range_deg: float = 5.0,
    lam_kJ_per_kg: float = 2450.0,
    cp_air_kJ_per_kgK: float = 1.005,
    rho_air_kg_per_m3: float = 1.2,
    I_inside_Wm2=None,        # 온실 내 광량(W/m2) → VPD 목표 추천에 사용
    verbose: bool = True,
) -> dict:
    """
    현재 T_now, RH_now 상태에서 VPD_target에 도달하기 위해
    냉방(ΔT) + 가습량을 조합해서 **단위 면적당(per m²)** 에너지가 최소인 전략 찾기.

    - VPD_target이 None이면 recommend_vpd_target(T_now, I_inside_Wm2)를 사용.
    - floor_area_m2는 항상 1.0으로 설정되어 있으므로 사용자로부터 입력받지 않는다.
    - height_m은 온실 층고로 입력받아 체적 계산에 사용된다.
    """
    # 1) VPD 목표 자동 설정
    if VPD_target is None:
        VPD_target = recommend_vpd_target(T_now, I_inside_Wm2)

    VPD_now = float(calc_vpd_kPa(T_now, RH_now))
    es_now = float(saturation_vapor_pressure_kPa(T_now))
    ea_now = es_now * RH_now / 100.0
    w_now = 0.622 * ea_now / (101.3 - ea_now)
    volume_m3 = floor_area_m2 * height_m
    m_air = rho_air_kg_per_m3 * volume_m3

    if verbose:
        print(f"[현재 상태] T={T_now:.2f}°C, RH={RH_now:.1f}%, VPD={VPD_now:.2f} kPa")
        print(f"[목표 VPD] target = {VPD_target:.2f} kPa")
        print(f"[온실 규모] {floor_area_m2:.1f} m² x {height_m:.1f} m → {volume_m3:.1f} m³")

    # 이미 목표 VPD 이하라면 추가 제어 없음
    if VPD_now <= VPD_target + 0.05:
        if verbose:
            print("[INFO] 이미 VPD가 목표 이하입니다. 추가 제어 필요 없음.")
        return {
            "status": "already_ok",
            "VPD_now": VPD_now,
            "VPD_target": VPD_target,
            "T_target": T_now,
            "RH_target": RH_now,
            "cooling_dT_C": 0.0,
            "water_L_total": 0.0,
            "water_L_per_m2": 0.0,
            "q_sens_kWh_per_m2": 0.0,
            "q_lat_kWh_per_m2": 0.0,
            "q_tot_kWh_per_m2": 0.0,
        }

    # 탐색할 온도 범위 (냉방만 고려)
    T_min = max(T_now - T_cool_range_deg, 10.0)
    T_candidates = np.linspace(T_now, T_min, 31)

    best = None

    for T_target in T_candidates:
        es_t = float(saturation_vapor_pressure_kPa(T_target))
        # VPD = es_t - ea_target = VPD_target → ea_target = es_t - VPD_target
        ea_target = es_t - VPD_target
        if ea_target <= 0:
            continue

        RH_target = ea_target / es_t * 100.0
        if RH_target > 100.0:
            continue

        w_target = 0.622 * ea_target / (101.3 - ea_target)

        # 제습(물 빼기)은 안 한다는 가정 → w_target >= w_now만 허용
        if w_target < w_now:
            continue

        # --- 냉방(현열) ---
        dT = max(0.0, T_now - T_target)
        Q_sens_kJ = m_air * cp_air_kJ_per_kgK * dT
        q_sens_kWh_per_m2 = (Q_sens_kJ / 3600.0) / floor_area_m2

        # --- 가습(잠열) ---
        delta_w = w_target - w_now
        m_H2O_kg = delta_w * m_air
        Q_lat_kJ = m_H2O_kg * lam_kJ_per_kg
        q_lat_kWh_per_m2 = (Q_lat_kJ / 3600.0) / floor_area_m2

        q_tot = q_sens_kWh_per_m2 + q_lat_kWh_per_m2

        candidate = {
            "T_target": float(T_target),
            "RH_target": float(RH_target),
            "VPD_target": float(VPD_target),
            "cooling_dT_C": float(dT),
            "water_L_total": float(m_H2O_kg),
            "water_L_per_m2": float(m_H2O_kg / floor_area_m2),
            "q_sens_kWh_per_m2": float(q_sens_kWh_per_m2),
            "q_lat_kWh_per_m2": float(q_lat_kWh_per_m2),
            "q_tot_kWh_per_m2": float(q_tot),
        }

        if best is None or candidate["q_tot_kWh_per_m2"] < best["q_tot_kWh_per_m2"]:
            best = candidate

    if best is None:
        if verbose:
            print("[WARN] 주어진 범위 내에서 VPD_target에 도달할 수 있는 조합을 찾지 못함.")
        return {
            "status": "no_feasible_solution",
            "VPD_now": VPD_now,
            "VPD_target": VPD_target,
        }

    if verbose:
        print("\n[최적 에너지 전략 (냉방+가습)]")
        print(f"- 목표 온도: {best['T_target']:.2f}°C (ΔT={best['cooling_dT_C']:.2f}°C 냉방)")
        print(f"- 목표 RH:   {best['RH_target']:.1f}% → VPD ≈ {best['VPD_target']:.2f} kPa")
        print(f"- 가습량:    온실 전체 {best['water_L_total']:.1f} L "
              f"(면적당 {best['water_L_per_m2']:.3f} L/m²)")
        print(f"- 에너지:    냉방 {best['q_sens_kWh_per_m2']:.4f} kWh/m², "
              f"가습(잠열) {best['q_lat_kWh_per_m2']:.4f} kWh/m²")
        print(f"            총 {best['q_tot_kWh_per_m2']:.4f} kWh/m²")

    best["status"] = "ok"
    best["VPD_now"] = float(VPD_now)
    return best


def print_user_notification(best: dict):
    """
    운영자(사용자)에게 보여줄 요약 알림
    """
    status = best.get("status")
    if status == "already_ok":
        print("[알림] 현재 VPD가 이미 목표 범위 이하입니다. 추가 제어 필요 없음.")
    elif status == "ok":
        print("[알림] 에너지 최소 VPD 제어 제안")
        print(f" - 목표 온도: {best['T_target']:.1f}°C (ΔT={best['cooling_dT_C']:.1f}°C 냉방)")
        print(f" - 목표 습도: {best['RH_target']:.1f}%")
        print(f" - 가습량: {best['water_L_per_m2']:.3f} L/m² (총 {best['water_L_total']:.1f} L)")
        print(f" - 면적당 총 에너지: {best['q_tot_kWh_per_m2']:.4f} kWh/m²")
    elif status == "no_feasible_solution":
        print("[알림] 주어진 제약 내에서 목표 VPD에 도달하기 어려움.")


# ============================================================
# 9. CSV 저장용 함수
# ============================================================
def save_results_to_csv(df: pd.DataFrame, output_path: str) -> None:
    """
    df 전체를 CSV 한 파일로 저장
    """
    df.to_csv(output_path, index=False)
    print(f"[SAVE] 결과를 CSV로 저장했습니다: {output_path}")


# ============================================================
# 9-1. 선택된 시점의 VPD 제어 솔루션 요약을 CSV로 저장
# ============================================================
def save_control_solution_to_csv(row, best, vpd_col, output_path: str):
    """
    row : df_to_control에서 선택된 1개 시점 (Series)
    best: suggest_low_energy_vpd_control() 반환 dict
    vpd_col: 사용한 VPD 컬럼 이름 ('vpd_measured' 또는 'vpd')
    """
    data = {
        # 측정 상태
        "datetime": row.get("datetime"),
        "T_measured": float(row.get("temperature", np.nan)),
        "RH_measured": float(row.get("humidity", np.nan)),
        "VPD_measured": float(row.get(vpd_col, np.nan)) if vpd_col is not None else np.nan,
        # 환기+차광(수동 제어) 후 모델 값
        "T_after_passive": float(row.get("T_in_model_shaded", np.nan)),
        "RH_after_passive": float(row.get("RH_model_shaded", np.nan)),
        "VPD_after_passive": float(row.get("vpd_model_shaded", np.nan)),
        # 목표 / 능동 제어 결과
        "VPD_target": float(best.get("VPD_target", np.nan)),
        "T_target": float(best.get("T_target", np.nan)),
        "RH_target": float(best.get("RH_target", np.nan)),
        "cooling_dT_C": float(best.get("cooling_dT_C", np.nan)),
        "water_L_total": float(best.get("water_L_total", np.nan)),
        "water_L_per_m2": float(best.get("water_L_per_m2", np.nan)),
        "q_sens_kWh_per_m2": float(best.get("q_sens_kWh_per_m2", np.nan)),
        "q_lat_kWh_per_m2": float(best.get("q_lat_kWh_per_m2", np.nan)),
        "q_tot_kWh_per_m2": float(best.get("q_tot_kWh_per_m2", np.nan)),
    }

    # 환기+차광만으로 목표 VPD에 도달 가능한지 여부 flag
    vpd_after = data["VPD_after_passive"]
    vpd_target = data["VPD_target"]
    if not pd.isna(vpd_after) and not pd.isna(vpd_target):
        data["passive_ok"] = vpd_after <= vpd_target + 0.05
    else:
        data["passive_ok"] = np.nan

    df_sol = pd.DataFrame([data])
    df_sol.to_csv(output_path, index=False)
    print(f"[SAVE] VPD 제어 솔루션 요약을 CSV로 저장했습니다: {output_path}")


# ============================================================
# 10. main() – 전체 흐름 + CSV 저장
# ============================================================
def main():
    # ASOS API 최대 호출 횟수
    MAX_ASOS_REQUESTS = 5

    # 1) 온실 10분 평균
    df_gh10 = make_greenhouse_10min(GROWTH_CSV_PATH)
    print("[GH] 온실 10분 평균 데이터 범위:",
          df_gh10["datetime"].min(), "~", df_gh10["datetime"].max())
    print("[GH] 10분 평균 데이터 예시:")
    print(df_gh10.head())

    # (옵션) CSV에 vpd 컬럼이 있으면, VPD >= 1.5 샘플 확인
    if "vpd" in df_gh10.columns:
        high_vpd = df_gh10[df_gh10["vpd"] >= 1.5]
        print(f"[GH] VPD >= 1.5 인 행 개수: {len(high_vpd)}")
        print("[GH] VPD >= 1.5 샘플 5행:")
        print(high_vpd[["datetime", "temperature", "humidity", "vpd"]].head())

    gh_start = df_gh10["datetime"].min()
    gh_end = df_gh10["datetime"].max()

    # 2) 온실과 가장 근접한 관측소 선택
    STN_ID = select_station_interactive()

    # 3) ASOS 시간자료
    df_asos_hourly = fetch_asos_hourly(
        stn_id=STN_ID,
        start_dt=gh_start.floor("H"),
        end_dt=gh_end.ceil("H"),
        service_key=SERVICE_KEY,
        max_requests=MAX_ASOS_REQUESTS,
    )

    print("[ASOS] 시간자료 행 수:", len(df_asos_hourly))
    if not df_asos_hourly.empty:
        print("[ASOS] 시간자료 범위:",
              df_asos_hourly["datetime"].min(), "~", df_asos_hourly["datetime"].max())
    else:
        print("[ASOS] 시간자료가 비어 있습니다. (max_requests 때문에 일부 구간만 가져왔을 수도 있음)")

    # 4) ASOS 10분 보간
    df_asos10 = make_asos_10min(df_asos_hourly, gh_start, gh_end)

    # 5) 온실 + ASOS 병합
    df_merged = merge_greenhouse_asos(df_gh10, df_asos10)
    print("[MERGE] 컬럼:", df_merged.columns.tolist())

    # 6) 시설/피복 선택
    facility_key, cover_type = choose_facility_and_cover()

    # 7) 환기창 개도각(전 기간 동일하게 가정)
    vent_angle_str = input("환기창 개도각(0~45도) 입력 (예: 30): ").strip()
    try:
        vent_angle = float(vent_angle_str)
    except ValueError:
        vent_angle = 0.0
    vent_angle = max(0.0, min(45.0, vent_angle))
    df_merged["vent_angle_deg"] = vent_angle

    # 8) 온실 층고(높이) 입력
    height_str = input("온실 층고(높이) 입력 (m, 예: 4.5): ").strip()
    try:
        gh_height = float(height_str)
    except ValueError:
        gh_height = 4.0  # 기본값
    if gh_height <= 0:
        print("[WARN] 층고가 0 이하로 입력되어 기본값 4.0 m를 사용합니다.")
        gh_height = 4.0

    # 단위면적 모델이므로 바닥면적은 1.0 m² 고정
    gh_floor_area = 1.0

    # 9) 차광 스크린 타입 (예시: 50%)
    screen_type = "screen_50"

    # 9-1) 열수지 + 차광 온도 모델
    df_with_shading = estimate_inside_temp_with_shading(
        df_merged=df_merged,
        cover_type=cover_type,
        screen_type=screen_type,
        gh_floor_area=gh_floor_area,
        gh_height=gh_height,
        ACH_base=2.0,
        use_dynamic_ACH=True,
        C_factor=3.0,
        frac_solar_to_air=0.4,
        time_col="datetime",
        vent_angle_col="vent_angle_deg",
        wind_col="ext_wind_ms",
    )

    # 9-2) 온실 내부로 들어오는 광량 모델 (시설별 골조율 반영)
    df_with_shading = add_inside_radiation_model(
        df_with_shading,
        facility_key=facility_key,
        cover_type=cover_type,
        screen_type=screen_type,
        k_internal=0.8,  # 작물/배드/기타 내부 감쇠
    )

    # 10) VPD까지 계산 (temperature / humidity가 있을 때만)
    df_with_vpd = None
    if {"temperature", "humidity"}.issubset(df_with_shading.columns):
        df_with_vpd = add_vpd_for_shading(df_with_shading)
        print("[RESULT] 온도/차광/VPD 예시 5행:")
        print(df_with_vpd[[
            "datetime",
            "ext_temp",
            "temperature",
            "T_in_model_noshade",
            "T_in_model_shaded",
            "deltaT_screen",
            "vpd_measured",
            "vpd_model_shaded",
            "deltaVPD_shading",
        ]].head())
    else:
        print("[RESULT] 온도/차광 예시 5행 (VPD는 계산 안 됨):")
        print(df_with_shading[[
            "datetime",
            "ext_temp",
            "T_in_model_noshade",
            "T_in_model_shaded",
            "deltaT_screen",
        ]].head())

    # 11) 전체 결과를 한 번에 CSV로 저장
    if df_with_vpd is not None:
        output_path = "/content/drive/MyDrive/final_project/vpd_shading_results_full_per_m2.csv"
        save_results_to_csv(df_with_vpd, output_path)
        df_to_control = df_with_vpd
    else:
        output_path = "/content/drive/MyDrive/final_project/vpd_shading_results_temp_only_per_m2.csv"
        save_results_to_csv(df_with_shading, output_path)
        df_to_control = df_with_shading

    # 12) VPD가 높은 시점 기준으로 VPD 제어 솔루션 계산
    if {"temperature", "humidity"}.issubset(df_to_control.columns) and not df_to_control.empty:

        # target_vpd = 1.5  # 고정하고 싶으면 이렇게; 자동이면 None
        target_vpd = None

        if "vpd_measured" in df_to_control.columns:
            vpd_col = "vpd_measured"
        elif "vpd" in df_to_control.columns:
            vpd_col = "vpd"
        else:
            vpd_col = None

        if vpd_col is not None:
            # 평균 이상 VPD 구간에서 가장 높은 시점 선택
            high_vpd_df = df_to_control[df_to_control[vpd_col] >=
                                        df_to_control[vpd_col].mean()].copy()
        else:
            high_vpd_df = pd.DataFrame()

        if not high_vpd_df.empty:
            high_vpd_df = high_vpd_df.sort_values(vpd_col, ascending=False)
            row = high_vpd_df.iloc[0]
            print(f"[CONTROL] VPD 높은 시점 선택: {row['datetime']}  (VPD={row[vpd_col]:.2f} kPa)")
        else:
            row = df_to_control.iloc[-1]
            print("[CONTROL] VPD가 평균보다 높은 시점이 없어 마지막 행 기준으로 계산합니다.")
            if vpd_col is not None:
                print(f"          (마지막 행 VPD={row[vpd_col]:.2f} kPa)")

        T_now = float(row["temperature"])  # 실제 온실 온도
        RH_now = float(row["humidity"])    # 실제 온실 RH
        I_inside = float(row.get("rad_model_shaded_Wm2", np.nan))

        # Stanghellini + VPD 차트 기반 목표 VPD 자동 적용 (target_vpd=None일 때)
        best = suggest_low_energy_vpd_control(
            T_now=T_now,
            RH_now=RH_now,
            VPD_target=target_vpd,     # None이면 recommend_vpd_target 사용
            floor_area_m2=gh_floor_area,
            height_m=gh_height,
            T_cool_range_deg=5.0,
            I_inside_Wm2=I_inside,
            verbose=True,
        )

        print()  # 줄 바꿈
        print_user_notification(best)      # 운영자 알림용 요약 (print 형식 그대로)

        # 지금 계산된 한 시점의 제어 솔루션을 별도 CSV로 저장
        control_csv_path = "/content/drive/MyDrive/final_project/vpd_control_solution_summary_per_m2.csv"
        save_control_solution_to_csv(row, best, vpd_col, control_csv_path)

    else:
        print("[INFO] temperature/humidity가 없어 VPD 제어 솔루션을 계산하지 않았습니다.")


if __name__ == "__main__":
    print("스크립트 문법 체크 OK (Colab에서는 main() 직접 호출해서 실행)")
    # Colab에서 사용할 때는 main()을 직접 호출하세요.