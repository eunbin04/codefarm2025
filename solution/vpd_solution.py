# solution/vpd_solution.py
import pandas as pd
import numpy as np
import requests

try:
    from google.colab import drive  # type: ignore
    drive.mount('/content/drive')
except Exception:
    print("[INFO] Colab 환경이 아니므로 drive.mount 생략")

# ---------------- 기본 설정 ----------------
STATION_DIR = "data/station_code.csv"
GROWTH_CSV_PATH = "data/mc_3m.csv"

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

FACILITY_FRAME_RATIO = {
    "glass_span": 0.80,
    "glass_venlo": 0.88,
    "rigid_house": 0.85,
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

COVER_MATERIALS = {
    "glass_single": {
        "name_kr": "단층 유리",
        "tau": 0.91,
        "U": 6.0,
    },
    "film_PE": {
        "name_kr": "PE 필름",
        "tau": 0.65,
        "U": 7.0,
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
    facility_key: str,
    cover_type: str,
    screen_type: str,
    k_internal: float = 0.8,
    ext_col: str = "ext_icsr_Wm2",
    prefix: str = "rad_model_",
) -> pd.DataFrame:
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
    frame_ratio = FACILITY_FRAME_RATIO[facility_key]

    G_ext = pd.to_numeric(df[ext_col], errors="coerce").fillna(0.0)

    G_in_noshade = G_ext * tau_cover * frame_ratio * k_internal
    G_in_shaded = G_ext * tau_cover * (1.0 - shading_rate) * frame_ratio * k_internal

    df[f"{prefix}noshade_Wm2"] = G_in_noshade
    df[f"{prefix}shaded_Wm2"] = G_in_shaded

    df[f"{prefix}noshade_lux"] = G_in_noshade / LUX_TO_WM2
    df[f"{prefix}shaded_lux"] = G_in_shaded / LUX_TO_WM2

    return df

# ============================================================
# 6. VPD/수증기 관련 함수
# ============================================================
def saturation_vapor_pressure_kPa(T_C):
    if isinstance(T_C, (pd.Series, pd.Index)):
        T = T_C.astype(float)
    else:
        T = pd.Series([T_C], dtype=float)
    es = 0.6108 * np.exp(17.27 * T / (T + 237.3))
    return es if isinstance(T_C, (pd.Series, pd.Index)) else es.iloc[0]

def calc_vpd_kPa(T_C, RH):
    es = saturation_vapor_pressure_kPa(T_C)
    if isinstance(RH, (pd.Series, pd.Index)):
        rh_frac = RH.astype(float) / 100.0
    else:
        rh_frac = float(RH) / 100.0
    ea = es * rh_frac
    vpd = es - ea
    return vpd

def recalc_rh_const_abs_humidity(T_old_C: pd.Series,
                                 RH_old: pd.Series,
                                 T_new_C: pd.Series) -> pd.Series:
    es_old = saturation_vapor_pressure_kPa(T_old_C)
    es_new = saturation_vapor_pressure_kPa(T_new_C)
    ea_old = es_old * (RH_old.astype(float) / 100.0)
    RH_new = (ea_old / es_new) * 100.0
    return RH_new.clip(lower=0.0, upper=100.0)

# ============================================================
# 6-1. 광·온도 기반 VPD 목표 추천
# ============================================================
def recommend_vpd_target(T_now, I_inside_Wm2=None):
    ppfd = None
    if I_inside_Wm2 is not None and not np.isnan(I_inside_Wm2):
        ppfd = I_inside_Wm2 * 2.0

    if ppfd is not None:
        if ppfd < 200:
            return 0.7
        elif ppfd < 400:
            return 0.9
        elif ppfd < 600:
            return 1.1
        elif ppfd < 800:
            return 1.3
        else:
            return 1.5

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
    U: float | None = None,
    ACH_base: float = 2.0,
    use_dynamic_ACH: bool = True,
    C_factor: float = 3.0,
    frac_solar_to_air: float = 0.4,
    time_col: str = "datetime",
    vent_angle_col: str = "vent_angle_deg",
    wind_col: str = "ext_wind_ms",
    default_dt_seconds: float = 600.0,
) -> pd.DataFrame:
    df = df_merged.copy()

    if cover_type not in COVER_MATERIALS:
        raise ValueError(f"알 수 없는 cover_type: {cover_type}")
    if screen_type not in SCREEN_MATERIALS:
        raise ValueError(f"알 수 없는 screen_type: {screen_type}")

    tau_cover = COVER_MATERIALS[cover_type]["tau"]
    shading_rate = SCREEN_MATERIALS[screen_type]["shading_rate"]
    u_factor_screen = SCREEN_MATERIALS[screen_type]["u_factor"]

    if U is None:
        U_cover = COVER_MATERIALS[cover_type].get("U", 6.0)
    else:
        U_cover = float(U)

    gh_volume = gh_floor_area * gh_height
    gh_envelope_area = gh_floor_area * 1.6

    rho_air = 1.2
    cp_air = 1000.0

    G_env_noshade = U_cover * gh_envelope_area
    G_env_shaded = U_cover * u_factor_screen * gh_envelope_area

    ach_series = compute_ACH_series(
        df,
        base_ACH=ACH_base,
        max_extra_ACH=30.0,
        vent_angle_col=vent_angle_col,
        wind_col=wind_col,
        use_dynamic=use_dynamic_ACH,
    )
    G_vent_series = rho_air * cp_air * (gh_height * ach_series / 3600.0)

    df["ACH"] = ach_series
    df["U_cover"] = U_cover
    df["U_screen_factor"] = u_factor_screen
    df["G_env_noshade"] = G_env_noshade
    df["G_env_shaded"] = G_env_shaded
    df["G_vent"] = G_vent_series
    df["G_loss_noshade"] = G_env_noshade + G_vent_series
    df["G_loss_shaded"] = G_env_shaded + G_vent_series

    G_ext = df.get("ext_icsr_Wm2", pd.Series(0.0, index=df.index)).fillna(0.0).astype(float)
    T_out = df.get("ext_temp", pd.Series(np.nan, index=df.index)).astype(float)

    Q_solar_noshade = G_ext * gh_floor_area * tau_cover
    Q_solar_shaded = G_ext * gh_floor_area * tau_cover * (1.0 - shading_rate)

    Q_air_noshade = Q_solar_noshade * frac_solar_to_air
    Q_air_shaded = Q_solar_shaded * frac_solar_to_air

    df["Q_solar_noshade"] = Q_solar_noshade
    df["Q_solar_shaded"] = Q_solar_shaded
    df["Q_air_noshade"] = Q_air_noshade
    df["Q_air_shaded"] = Q_air_shaded

    if time_col in df.columns:
        times = pd.to_datetime(df[time_col])
    elif isinstance(df.index, pd.DatetimeIndex):
        times = df.index
    else:
        times = pd.date_range("2000-01-01", periods=len(df), freq=f"{int(default_dt_seconds)}S")

    df["_time_for_dt"] = times
    dt_seconds = df["_time_for_dt"].diff().dt.total_seconds().fillna(default_dt_seconds)
    dt_seconds = dt_seconds.clip(lower=1.0)

    C_air = rho_air * cp_air * gh_volume
    C_eff = C_factor * C_air

    n = len(df)
    T_in_noshade = np.zeros(n, dtype=float)
    T_in_shaded = np.zeros(n, dtype=float)

    if "temperature" in df.columns and not df["temperature"].isna().all():
        T_init = float(df["temperature"].iloc[0])
    else:
        T_init = float(T_out.iloc[0]) if not np.isnan(T_out.iloc[0]) else 20.0

    T_in_noshade[0] = T_init
    T_in_shaded[0] = T_init

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

    df["share_env_loss_noshade"] = G_env_noshade / df["G_loss_noshade"]
    df["share_vent_loss_noshade"] = df["G_vent"] / df["G_loss_noshade"]
    df["share_env_loss_shaded"] = G_env_shaded / df["G_loss_shaded"]
    df["share_vent_loss_shaded"] = df["G_vent"] / df["G_loss_shaded"]

    if "temperature" in df.columns:
        df["T_measured"] = df["temperature"].astype(float)
        df["error_measured_vs_model_shaded"] = df["T_measured"] - df["T_in_model_shaded"]

    return df

def add_vpd_for_shading(df_with_shading: pd.DataFrame) -> pd.DataFrame:
    df = df_with_shading.copy()
    for col in ["temperature", "humidity", "T_in_model_shaded"]:
        if col not in df.columns:
            raise KeyError(f"'{col}' 컬럼이 없습니다.")

    T_meas = df["temperature"].astype(float)
    RH_meas = df["humidity"].astype(float)

    df["vpd_measured"] = calc_vpd_kPa(T_meas, RH_meas)

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
    VPD_target=None,
    floor_area_m2: float = 1.0,
    height_m: float = 4.0,
    T_cool_range_deg: float = 5.0,
    lam_kJ_per_kg: float = 2450.0,
    cp_air_kJ_per_kgK: float = 1.005,
    rho_air_kg_per_m3: float = 1.2,
    I_inside_Wm2=None,
    verbose: bool = True,
) -> dict:
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

    T_min = max(T_now - T_cool_range_deg, 10.0)
    T_candidates = np.linspace(T_now, T_min, 31)

    best = None

    for T_target in T_candidates:
        es_t = float(saturation_vapor_pressure_kPa(T_target))
        ea_target = es_t - VPD_target
        if ea_target <= 0:
            continue

        RH_target = ea_target / es_t * 100.0
        if RH_target > 100.0:
            continue

        w_target = 0.622 * ea_target / (101.3 - ea_target)

        if w_target < w_now:
            continue

        dT = max(0.0, T_now - T_target)
        Q_sens_kJ = m_air * cp_air_kJ_per_kgK * dT
        q_sens_kWh_per_m2 = (Q_sens_kJ / 3600.0) / floor_area_m2

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
    df.to_csv(output_path, index=False)
    print(f"[SAVE] 결과를 CSV로 저장했습니다: {output_path}")

def save_control_solution_to_csv(row, best, vpd_col, output_path: str):
    data = {
        "datetime": row.get("datetime"),
        "T_measured": float(row.get("temperature", np.nan)),
        "RH_measured": float(row.get("humidity", np.nan)),
        "VPD_measured": float(row.get(vpd_col, np.nan)) if vpd_col is not None else np.nan,
        "T_after_passive": float(row.get("T_in_model_shaded", np.nan)),
        "RH_after_passive": float(row.get("RH_model_shaded", np.nan)),
        "VPD_after_passive": float(row.get("vpd_model_shaded", np.nan)),
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

    vpd_after = data["VPD_after_passive"]
    vpd_target = data["VPD_target"]
    if not pd.isna(vpd_after) and not pd.isna(vpd_target):
        data["passive_ok"] = vpd_after <= vpd_target + 0.05
    else:
        data["passive_ok"] = np.nan

    df_sol = pd.DataFrame([data])
    df_sol.to_csv(output_path, index=False)
    print(f"[SAVE] VPD 제어 솔루션 요약을 CSV로 저장했습니다: {output_path}")

###############################################################################
# Additional psychrometric helpers
###############################################################################
DEFAULT_EXT_RH = 70.0
DEFAULT_ATM_PRESS_KPA = 101.325
DEFAULT_WIND_MS = 1.0

def compute_humidity_ratio(T_C: pd.Series, RH: pd.Series,
                           P_kPa: float = DEFAULT_ATM_PRESS_KPA) -> pd.Series:
    es = saturation_vapor_pressure_kPa(T_C)
    pv = es * (RH.astype(float) / 100.0)
    w = 0.62198 * pv / (P_kPa - pv)
    return w

def compute_specific_enthalpy(T_C: pd.Series, w: pd.Series) -> pd.Series:
    cp_da = 1.006
    cp_wv = 1.86
    h_fg = 2501.0
    T = T_C.astype(float)
    w = w.astype(float)
    h = cp_da * T + w * (h_fg + cp_wv * T)
    return h

def compute_enthalpy_and_abs_humidity(df: pd.DataFrame,
                                      temp_col: str = "temperature",
                                      rh_col: str = "humidity",
                                      ext_temp_col: str = "ext_temp",
                                      ext_rh_col: str = "ext_rh",
                                      pressure_kPa: float = DEFAULT_ATM_PRESS_KPA
                                      ) -> pd.DataFrame:
    df = df.copy()
    if {temp_col, rh_col}.issubset(df.columns):
        w_in = compute_humidity_ratio(df[temp_col], df[rh_col], P_kPa=pressure_kPa)
        df["w_in_kg_per_kg"] = w_in
        df["h_in_kJ_per_kgda"] = compute_specific_enthalpy(df[temp_col], w_in)
        rho_air = 1.2
        df["abs_hum_in_kg_per_m3"] = (rho_air * w_in) / (1.0 + w_in)
    else:
        df["w_in_kg_per_kg"] = np.nan
        df["h_in_kJ_per_kgda"] = np.nan
        df["abs_hum_in_kg_per_m3"] = np.nan

    if ext_temp_col in df.columns:
        T_ext = df[ext_temp_col].astype(float)
    else:
        T_ext = pd.Series(np.nan, index=df.index)

    if ext_rh_col in df.columns:
        RH_ext = df[ext_rh_col].astype(float)
        df["ext_rh_assumed"] = False
    else:
        RH_ext = pd.Series(DEFAULT_EXT_RH, index=df.index)
        df["ext_rh_assumed"] = True

    w_out = compute_humidity_ratio(T_ext, RH_ext, P_kPa=pressure_kPa)
    df["w_out_kg_per_kg"] = w_out
    df["h_out_kJ_per_kgda"] = compute_specific_enthalpy(T_ext, w_out)
    rho_air = 1.2
    df["abs_hum_out_kg_per_m3"] = (rho_air * w_out) / (1.0 + w_out)
    return df

def w_to_relative_humidity(w: pd.Series, T_C: pd.Series,
                           P_kPa: float = DEFAULT_ATM_PRESS_KPA) -> pd.Series:
    pv = (P_kPa * w) / (0.62198 + w)
    es = saturation_vapor_pressure_kPa(T_C)
    RH = (pv / es) * 100.0
    return RH.clip(lower=0.0, upper=100.0)

def compute_ventilation_humidity_removal(
    df: pd.DataFrame,
    height_m: float,
    floor_area_m2: float = 1.0,
    ach_col: str = "ACH",
    temp_in_col: str = "temperature",
    rh_in_col: str = "humidity",
    temp_out_col: str = "ext_temp",
    rh_out_col: str = "ext_rh",
    pressure_kPa: float = DEFAULT_ATM_PRESS_KPA,
    dt_seconds: float | None = None,
) -> pd.DataFrame:
    df = df.copy()
    df = compute_enthalpy_and_abs_humidity(df,
                                           temp_col=temp_in_col,
                                           rh_col=rh_in_col,
                                           ext_temp_col=temp_out_col,
                                           ext_rh_col=rh_out_col,
                                           pressure_kPa=pressure_kPa)

    volume_m3 = floor_area_m2 * height_m
    rho_air = 1.2

    if dt_seconds is not None:
        dt_series = pd.Series(dt_seconds, index=df.index)
    else:
        if "datetime" in df.columns:
            times = pd.to_datetime(df["datetime"])
            dt_series = times.diff().dt.total_seconds().fillna(600.0)
        else:
            dt_series = pd.Series(600.0, index=df.index)

    w_in = df["w_in_kg_per_kg"].astype(float)
    w_out = df["w_out_kg_per_kg"].astype(float)
    dw = (w_in - w_out).clip(lower=0.0)

    if ach_col in df.columns:
        ach_series = df[ach_col].astype(float).fillna(0.0)
    else:
        ach_series = pd.Series(0.1, index=df.index)

    removal_rate = rho_air * volume_m3 * (ach_series / 3600.0) * dw
    water_removed = removal_rate * dt_series
    df["water_removed_kg_per_m2"] = water_removed
    delta_w = water_removed / (rho_air * volume_m3)
    w_after = (w_in - delta_w).clip(lower=0.0)
    df["w_after_vent"] = w_after
    df["RH_after_vent"] = w_to_relative_humidity(w_after, df[temp_in_col], P_kPa=pressure_kPa)
    return df

###############################################################################
# Evaporative cooling (mist) and three‑stage VPD estimation
###############################################################################
def compute_saturation_humidity_ratio(T_C: float | pd.Series,
                                      P_kPa: float = DEFAULT_ATM_PRESS_KPA) -> float | pd.Series:
    es = saturation_vapor_pressure_kPa(T_C)
    w_sat = 0.62198 * es / (P_kPa - es)
    return w_sat

def apply_mist_cooling(T1: float,
                       w1: float,
                       Q_mist_kcal: float,
                       height_m: float,
                       floor_area_m2: float = 1.0,
                       C_factor: float = 3.0,
                       latent_heat_kJ_per_kg: float = 2450.0,
                       P_kPa: float = DEFAULT_ATM_PRESS_KPA) -> tuple[float, float, float, float]:
    Q_mist_kJ = Q_mist_kcal * 4.184
    volume_m3 = floor_area_m2 * height_m
    rho_air = 1.2
    m_air = rho_air * volume_m3
    w_sat1 = compute_saturation_humidity_ratio(T1, P_kPa=P_kPa)
    delta_w_needed = max(0.0, float(w_sat1) - w1)
    m_evap_max = delta_w_needed * m_air
    Q_evap_max_kJ = m_evap_max * latent_heat_kJ_per_kg

    if Q_mist_kJ <= Q_evap_max_kJ + 1e-9:
        m_evap = Q_mist_kJ / latent_heat_kJ_per_kg
        w2 = w1 + m_evap / m_air
        Q_evap_kJ = Q_mist_kJ
        T2 = T1
    else:
        m_evap = m_evap_max
        w2 = w_sat1
        Q_evap_kJ = Q_evap_max_kJ
        Q_remain_kJ = Q_mist_kJ - Q_evap_kJ
        C_air = rho_air * 1000.0 * volume_m3
        C_eff_kJ_per_K = C_factor * C_air / 1000.0
        dT = Q_remain_kJ / C_eff_kJ_per_K
        T2 = T1 - dT
    return T2, w2, m_evap, Q_evap_kJ

def compute_three_stage_vpd(df: pd.DataFrame,
                            height_m: float,
                            floor_area_m2: float = 1.0,
                            Q_mist_kcal: float = 580.0,
                            vpd_threshold: float = 1.5,
                            C_factor: float = 3.0,
                            P_kPa: float = DEFAULT_ATM_PRESS_KPA) -> pd.DataFrame:
    results = df.copy()
    results["VPD_stage1"] = np.nan
    results["VPD_stage2"] = np.nan
    results["VPD_stage3"] = np.nan
    results["T_stage1"] = np.nan
    results["T_stage2"] = np.nan
    results["T_stage3"] = np.nan
    results["RH_stage1"] = np.nan
    results["RH_stage2"] = np.nan
    results["RH_stage3"] = np.nan
    results["energy_stage3_kWh_per_m2"] = np.nan
    results["q_sens_stage3_kWh_per_m2"] = np.nan
    results["q_lat_stage3_kWh_per_m2"] = np.nan

    for idx, row in results.iterrows():
        if "T_in_model_shaded" in row and not pd.isna(row["T_in_model_shaded"]):
            T1 = float(row["T_in_model_shaded"])
            RH1 = float(row.get("RH_after_vent", row.get("RH_model_shaded", np.nan)))
        else:
            T1 = float(row.get("temperature", np.nan))
            RH1 = float(row.get("humidity", np.nan))
        if pd.isna(T1) or pd.isna(RH1):
            continue
        results.at[idx, "T_stage1"] = T1
        results.at[idx, "RH_stage1"] = RH1
        VPD1 = calc_vpd_kPa(T1, RH1)
        results.at[idx, "VPD_stage1"] = float(VPD1)

        w1 = float(compute_humidity_ratio(pd.Series([T1]), pd.Series([RH1]), P_kPa=P_kPa).iloc[0])

        if VPD1 > vpd_threshold:
            T2 = T1
            RH2 = RH1
            VPD2 = VPD1
        else:
            T2_tmp, w2_tmp, m_evap, Q_evap_kJ = apply_mist_cooling(T1, w1,
                                                                    Q_mist_kcal=Q_mist_kcal,
                                                                    height_m=height_m,
                                                                    floor_area_m2=floor_area_m2,
                                                                    C_factor=C_factor,
                                                                    latent_heat_kJ_per_kg=2450.0,
                                                                    P_kPa=P_kPa)
            RH2_tmp = float(w_to_relative_humidity(pd.Series([w2_tmp]), pd.Series([T2_tmp]), P_kPa=P_kPa).iloc[0])
            VPD2_tmp = float(calc_vpd_kPa(T2_tmp, RH2_tmp))
            T2 = T2_tmp
            RH2 = RH2_tmp
            VPD2 = VPD2_tmp
        results.at[idx, "T_stage2"] = T2
        results.at[idx, "RH_stage2"] = RH2
        results.at[idx, "VPD_stage2"] = VPD2

        if VPD2 <= vpd_threshold:
            results.at[idx, "T_stage3"] = T2
            results.at[idx, "RH_stage3"] = RH2
            results.at[idx, "VPD_stage3"] = VPD2
            results.at[idx, "energy_stage3_kWh_per_m2"] = 0.0
            results.at[idx, "q_sens_stage3_kWh_per_m2"] = 0.0
            results.at[idx, "q_lat_stage3_kWh_per_m2"] = 0.0
        else:
            best = suggest_low_energy_vpd_control(
                T_now=T2,
                RH_now=RH2,
                VPD_target=None,
                floor_area_m2=floor_area_m2,
                height_m=height_m,
                T_cool_range_deg=5.0,
                I_inside_Wm2=row.get("rad_model_shaded_Wm2", np.nan),
                verbose=False,
            )
            T3 = float(best.get("T_target", T2))
            RH3 = float(best.get("RH_target", RH2))
            VPD3 = float(calc_vpd_kPa(T3, RH3))
            results.at[idx, "T_stage3"] = T3
            results.at[idx, "RH_stage3"] = RH3
            results.at[idx, "VPD_stage3"] = VPD3
            results.at[idx, "energy_stage3_kWh_per_m2"] = float(best.get("q_tot_kWh_per_m2", 0.0))
            results.at[idx, "q_sens_stage3_kWh_per_m2"] = float(best.get("q_sens_kWh_per_m2", 0.0))
            results.at[idx, "q_lat_stage3_kWh_per_m2"] = float(best.get("q_lat_kWh_per_m2", 0.0))
    return results

###############################################################################
# Main execution flow
###############################################################################
def main():
    df_gh10 = make_greenhouse_10min(GROWTH_CSV_PATH)
    print("[GH] 온실 10분 평균 데이터 범위:",
          df_gh10["datetime"].min(), "~", df_gh10["datetime"].max())

    gh_start = df_gh10["datetime"].min()
    gh_end = df_gh10["datetime"].max()

    STN_ID = select_station_interactive()

    df_asos_hourly = fetch_asos_hourly(
        stn_id=STN_ID,
        start_dt=gh_start.floor("H"),
        end_dt=gh_end.ceil("H"),
        service_key=SERVICE_KEY,
        max_requests=5,
    )
    df_asos10 = make_asos_10min(df_asos_hourly, gh_start, gh_end)

    df_merged = merge_greenhouse_asos(df_gh10, df_asos10)

    facility_key, cover_type = choose_facility_and_cover()

    vent_angle_str = input("환기창 개도각(0~45도) 입력 (예: 30): ").strip()
    try:
        vent_angle = float(vent_angle_str)
    except ValueError:
        vent_angle = 0.0
    vent_angle = max(0.0, min(45.0, vent_angle))
    df_merged["vent_angle_deg"] = vent_angle

    height_str = input("온실 층고(높이) 입력 (m, 예: 4.5): ").strip()
    try:
        gh_height = float(height_str)
    except ValueError:
        gh_height = 4.0
    if gh_height <= 0:
        print("[WARN] 층고가 0 이하로 입력되어 기본값 4.0 m를 사용합니다.")
        gh_height = 4.0

    gh_floor_area = 1.0

    screen_type = "screen_50"

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

    df_with_shading = add_inside_radiation_model(
        df_with_shading,
        facility_key=facility_key,
        cover_type=cover_type,
        screen_type=screen_type,
        k_internal=0.8,
    )

    df_with_psy = compute_enthalpy_and_abs_humidity(df_with_shading)
    print("[PSY] 내부/외부 엔탈피 및 절대습도 계산 완료. 예시:")
    print(df_with_psy[[
        "datetime", "h_in_kJ_per_kgda", "h_out_kJ_per_kgda",
        "abs_hum_in_kg_per_m3", "abs_hum_out_kg_per_m3"
    ]].head())

    df_with_vent = compute_ventilation_humidity_removal(
        df_with_psy,
        height_m=gh_height,
        floor_area_m2=gh_floor_area,
        ach_col="ACH",
        temp_in_col="temperature",
        rh_in_col="humidity",
        temp_out_col="ext_temp",
        rh_out_col="ext_rh",
    )
    print("[VENT] 환기로 인한 수증기 제거 계산 완료. 예시:")
    print(df_with_vent[[
        "datetime",
        "temperature",
        "humidity",
        "RH_after_vent",
        "water_removed_kg_per_m2"
    ]].head())

    if {"temperature", "humidity"}.issubset(df_with_vent.columns):
        df_with_vpd = add_vpd_for_shading(df_with_vent)
    else:
        df_with_vpd = df_with_vent

    df_three_stage = compute_three_stage_vpd(
        df_with_vpd,
        height_m=gh_height,
        floor_area_m2=gh_floor_area,
        Q_mist_kcal=580.0,
        vpd_threshold=1.5,
        C_factor=3.0,
        P_kPa=DEFAULT_ATM_PRESS_KPA,
    )

    three_stage_csv_path = "vpd_three_stage_results_per_m2_modified.csv"
    save_results_to_csv(df_three_stage, three_stage_csv_path)

    if {"VPD_stage1", "VPD_stage2", "VPD_stage3"}.issubset(df_three_stage.columns) and not df_three_stage.empty:
        high_vpd_df = df_three_stage[df_three_stage["VPD_stage1"] >= df_three_stage["VPD_stage1"].mean()].copy()
        if not high_vpd_df.empty:
            high_vpd_df = high_vpd_df.sort_values("VPD_stage1", ascending=False)
            sel_row = high_vpd_df.iloc[0]
        else:
            sel_row = df_three_stage.iloc[-1]

        best = suggest_low_energy_vpd_control(
            T_now=float(sel_row["T_stage2"]),
            RH_now=float(sel_row["RH_stage2"]),
            VPD_target=1.5,
            floor_area_m2=gh_floor_area,
            height_m=gh_height,
            T_cool_range_deg=5.0,
            I_inside_Wm2=sel_row.get("rad_model_shaded_Wm2", np.nan),
            verbose=True,
        )
        print()
        print_user_notification(best)
        print(f"[에너지] 냉방: {best['q_sens_kWh_per_m2']:.4f} kWh/m², "
              f"가습: {best['q_lat_kWh_per_m2']:.4f} kWh/m², "
              f"총: {best['q_tot_kWh_per_m2']:.4f} kWh/m²")

        control_csv_path = "vpd_control_solution_summary_per_m2_three_stage.csv"
        vpd_col_sel = "VPD_stage2" if not pd.isna(sel_row["VPD_stage2"]) else None
        save_control_solution_to_csv(sel_row, best, vpd_col_sel, control_csv_path)

if __name__ == "__main__":
    print("수정된 스크립트를 실행합니다.")
    main()
