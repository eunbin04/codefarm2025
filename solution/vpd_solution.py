# solution/vpd_solution.py
import pandas as pd
import numpy as np
import requests

# ====================== 설정 ======================
STATION_DIR = "data/station_code.csv"
GROWTH_CSV_PATH = "mc_3m.csv"
ASOS_URL = "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"

# 출력 파일 경로들 (상대경로로 통일)
output_path = "merged_all_10min.csv"
output_shading_path = "merged_with_shading_temp.csv"
vpd_output_path = "merged_with_shading_temp_vpd_sensitivity.csv"
vpd_vent_output = "merged_with_shading_temp_ventsim.csv"
controlcsvpath = "vpdcontrolsolutionsummaryperm2.csv"

# ================== 1. 온실 10분 평균 만들기 ==================
LUX_TO_WM2 = 0.0083

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
                stn_code = int(row["지점"])
                return stn_name, stn_code
        except ValueError:
            pass
        print("잘못된 입력입니다. 다시 입력해 주세요.")

def select_station_interactive() -> str:
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

def make_greenhouse_10min(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    df["datetime"] = pd.to_datetime(
        df["date_time"].str.replace(" T ", " "),
        errors="coerce"
    )
    df = df.set_index("datetime")
    cols_to_avg = ["temperature", "humidity", "vpd", "light"]
    df_10min = df[cols_to_avg].resample("10min").mean().reset_index()
    df_10min["light_lux"] = df_10min["light"]
    df_10min["light_Wm2"] = df_10min["light"] * LUX_TO_WM2
    return df_10min

# ================== 2. 기상청 ASOS 시간자료 호출 ==================
def fetch_asos_hourly(stn_id: str, start_dt: pd.Timestamp, end_dt: pd.Timestamp, service_key: str) -> pd.DataFrame:
    all_items = []
    current_start_dt = start_dt
    while current_start_dt <= end_dt:
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
        
        if resp.status_code != 200:
            print("[ASOS] 에러 응답:")
            print(resp.text[:500])
            current_start_dt += pd.Timedelta(days=1)
            continue
        
        data = resp.json()
        try:
            items = data["response"]["body"]["items"]["item"]
            if items:
                all_items.extend(items)
        except KeyError:
            print("[ASOS] items 없음 / 구조 이상:")
            print(data)
        
        current_start_dt = current_end_dt + pd.Timedelta(days=1)
    
    if not all_items:
        print("[ASOS] 데이터 없음")
        return pd.DataFrame()
    
    rows = []
    for it in all_items:
        rows.append({
            "datetime": it.get("tm"),
            "ext_temp": it.get("ta"),
            "ext_rh": it.get("hm"),
            "ext_icsr_MJ": it.get("icsr")
        })
    
    df_hourly = pd.DataFrame(rows)
    df_hourly["datetime"] = pd.to_datetime(df_hourly["datetime"], format="%Y-%m-%d %H:%M", errors="coerce")
    df_hourly["ext_temp"] = pd.to_numeric(df_hourly["ext_temp"], errors="coerce")
    df_hourly["ext_rh"] = pd.to_numeric(df_hourly["ext_rh"], errors="coerce")
    df_hourly["ext_icsr_MJ"] = pd.to_numeric(df_hourly["ext_icsr_MJ"], errors="coerce").fillna(0)
    df_hourly["ext_icsr_Wm2"] = df_hourly["ext_icsr_MJ"] * (1_000_000 / 3600.0)
    return df_hourly

# ================== 3. ASOS 시간자료 → 10분 단위로 보간 ==================
def make_asos_10min(df_hourly: pd.DataFrame, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
    if df_hourly.empty:
        print("[ASOS] 시간자료 DF가 비어있음")
        return df_hourly
    df_hourly = df_hourly.set_index("datetime").sort_index()
    start_10 = start_dt.floor("10min")
    end_10 = end_dt.ceil("10min")
    idx_10min = pd.date_range(start_10, end_10, freq="10min")
    df_10min_ext = df_hourly.reindex(idx_10min).interpolate(method="time")
    df_10min_ext = df_10min_ext.reset_index().rename(columns={"index": "datetime"})
    return df_10min_ext

# ================== 4. 온실 10분 평균 + 외부(ASOS) 10분 자료 병합 ==================
def merge_greenhouse_with_asos(stn_id: str):
    df_gh_10 = make_greenhouse_10min(GROWTH_CSV_PATH)
    print("[GH] 온실 10분 평균 행 수:", len(df_gh_10))
    start_dt = df_gh_10["datetime"].min()
    end_dt = df_gh_10["datetime"].max()
    print("[기간] 온실 데이터:", start_dt, "~", end_dt)
    
    df_asos_hour = fetch_asos_hourly(stn_id, start_dt, end_dt, SERVICE_KEY)
    print("[ASOS] 시간자료 행 수:", len(df_asos_hour))
    
    if df_asos_hour.empty:
        print("[WARN] ASOS 시간자료가 비어있어서 외기 데이터 없이 온실 데이터만 반환합니다.")
        return df_gh_10
    
    df_asos_10 = make_asos_10min(df_asos_hour, start_dt, end_dt)
    print("[ASOS] 10분 보간 행 수:", len(df_asos_10))
    
    df_merged = pd.merge(
        df_gh_10,
        df_asos_10,
        how="left",
        on="datetime"
    )
    
    print("[최종 병합 미리보기]")
    print(df_merged[[
        "datetime",
        "temperature", "humidity", "vpd",
        "light_lux", "light_Wm2",
        "ext_temp", "ext_rh", "ext_icsr_MJ", "ext_icsr_Wm2"
    ]].head().to_string(index=False))
    
    df_merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[INFO] 병합 데이터 CSV 저장 완료: {output_path}")
    return df_merged

# ================== 5. 피복재/차광스크린 설정 ==================
COVER_MATERIALS = {
    "glass_single": {"name_kr": "단층 유리", "tau": 0.70, "U": 6.0},
    "pe_single": {"name_kr": "단층 PE필름", "tau": 0.65, "U": 7.0},
    "pe_double": {"name_kr": "이중 PE필름", "tau": 0.55, "U": 6.5},
}

SCREEN_MATERIALS = {
    "none": {"name_kr": "차광 없음", "shading_rate": 0.0},
    "screen_35": {"name_kr": "차광스크린 35%", "shading_rate": 0.35},
    "screen_50": {"name_kr": "차광스크린 50%", "shading_rate": 0.50},
    "screen_70": {"name_kr": "차광스크린 70%", "shading_rate": 0.70},
}

def estimate_inside_temp_with_shading(
    df_merged: pd.DataFrame,
    cover_type: str,
    screen_type: str,
    gh_floor_area: float,
    gh_height: float,
    U: float = 6.0,
    ACH: float = 20.0,
) -> pd.DataFrame:
    df = df_merged.copy()
    
    tau_cover = COVER_MATERIALS[cover_type]["tau"]
    S_screen = SCREEN_MATERIALS[screen_type]["shading_rate"]
    
    gh_volume = gh_floor_area * gh_height
    gh_envelope_area = gh_floor_area * 1.6
    rho_air = 1.2
    cp_air = 1000.0
    G_env = U * gh_envelope_area
    G_vent = rho_air * cp_air * (gh_volume * ACH / 3600.0)
    G_loss = G_env + G_vent
    
    G_ext = df.get("ext_icsr_Wm2", pd.Series(0.0, index=df.index)).fillna(0.0)
    T_out = df.get("ext_temp", pd.Series(pd.NA, index=df.index))
    
    Q_solar_noshade = G_ext * gh_floor_area * tau_cover
    Q_solar_shaded = G_ext * gh_floor_area * tau_cover * (1.0 - S_screen)
    
    df["T_in_model_noshade"] = T_out + (Q_solar_noshade / G_loss)
    df["T_in_model_shaded"] = T_out + (Q_solar_shaded / G_loss)
    df["deltaT_screen"] = df["T_in_model_noshade"] - df["T_in_model_shaded"]
    
    if "temperature" in df.columns:
        df["T_measured"] = df["temperature"]
        df["error_measured_vs_model_shaded"] = df["T_measured"] - df["T_in_model_shaded"]
    
    return df

# ================== 6. VPD 민감도 계산 ==================
def sat_vapor_pressure_kpa(T_c):
    T = np.asarray(T_c, dtype="float64")
    return 0.6108 * np.exp((17.27 * T) / (T + 237.3))

def calc_vpd_kPa(T_c, RH_percent):
    es = sat_vapor_pressure_kpa(T_c)
    ea = RH_percent / 100.0 * es
    return es - ea

def add_vpd_sensitivity_using_dewpoint(df_merged: pd.DataFrame) -> pd.DataFrame:
    df = df_merged.copy()
    
    if "dew_point" not in df.columns:
        T = df["temperature"].astype("float64")
        RH = df["humidity"].astype("float64")
        rh_frac = RH / 100.0
        valid = T.notna() & rh_frac.notna() & (rh_frac > 0) & (rh_frac <= 1)
        a, b = 17.27, 237.3
        gamma = np.log(rh_frac[valid]) + (a * T[valid]) / (b + T[valid])
        T_dew = (b * gamma) / (a - gamma)
        df.loc[valid, "dew_point"] = T_dew
    
    mask = df["temperature"].notna() & df["dew_point"].notna()
    T_air = df.loc[mask, "temperature"]
    T_dew = df.loc[mask, "dew_point"]
    
    ea = sat_vapor_pressure_kpa(T_dew)
    es_air = sat_vapor_pressure_kpa(T_air)
    vpd_from_dew = es_air - ea
    
    df.loc[mask, "ea_kPa"] = ea
    df.loc[mask, "es_air_kPa"] = es_air
    df.loc[mask, "vpd_from_dew_kPa"] = vpd_from_dew
    
    for dT in (1.0, 2.0, 3.0):
        T_new = T_air + dT
        es_new = sat_vapor_pressure_kpa(T_new)
        vpd_new = es_new - ea
        df.loc[mask, f"vpd_plus_{int(dT)}C_kPa"] = vpd_new
        df.loc[mask, f"delta_vpd_plus_{int(dT)}C_kPa"] = vpd_new - vpd_from_dew
    
    if "T_in_model_noshade" in df.columns:
        T_model_ns = df.loc[mask, "T_in_model_noshade"]
        vpd_model_ns = sat_vapor_pressure_kpa(T_model_ns) - ea
        df.loc[mask, "vpd_T_in_model_noshade_kPa"] = vpd_model_ns
    
    if "T_in_model_shaded" in df.columns:
        T_model_sh = df.loc[mask, "T_in_model_shaded"]
        vpd_model_sh = sat_vapor_pressure_kpa(T_model_sh) - ea
        df.loc[mask, "vpd_T_in_model_shaded_kPa"] = vpd_model_sh
    
    return df

# ================== 7. 환기 효과 시뮬레이션 ==================
def add_ea_in_out_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "dew_point" in df.columns:
        mask_dp = df["dew_point"].notna()
        df.loc[mask_dp, "ea_in_obs_kPa"] = sat_vapor_pressure_kpa(df.loc[mask_dp, "dew_point"])
    elif "temperature" in df.columns and "humidity" in df.columns:
        mask_trh = df["temperature"].notna() & df["humidity"].notna()
        es_in = sat_vapor_pressure_kpa(df.loc[mask_trh, "temperature"])
        rh_frac = df.loc[mask_trh, "humidity"] / 100.0
        df.loc[mask_trh, "ea_in_obs_kPa"] = es_in * rh_frac
    
    if "ext_temp" in df.columns and "ext_rh" in df.columns:
        mask_ext = df["ext_temp"].notna() & df["ext_rh"].notna()
        es_out = sat_vapor_pressure_kpa(df.loc[mask_ext, "ext_temp"])
        rh_out = df.loc[mask_ext, "ext_rh"] / 100.0
        df.loc[mask_ext, "ea_out_kPa"] = es_out * rh_out
    return df

def simulate_ventilation_effect_simple(df_input: pd.DataFrame, vent_angle_deg: float, vent_angle_max_deg: float = 45.0, temp_base_col: str = "T_in_model_shaded", prefix: str = "vent_") -> pd.DataFrame:
    df = add_ea_in_out_columns(df_input)
    mask = (df["ea_in_obs_kPa"].notna() & df["ea_out_kPa"].notna() & df["ext_temp"].notna())
    
    vent_frac = vent_angle_deg / vent_angle_max_deg
    vent_frac = max(0.0, min(1.0, vent_frac))
    
    df[prefix + "angle_deg"] = vent_angle_deg
    df[prefix + "frac"] = vent_frac
    
    if temp_base_col in df.columns:
        T_base = df.loc[mask, temp_base_col]
    else:
        T_base = df.loc[mask, "temperature"]
    
    T_out = df.loc[mask, "ext_temp"]
    T_after = (1.0 - vent_frac) * T_base + vent_frac * T_out
    
    df.loc[mask, prefix + "T_before_C"] = T_base
    df.loc[mask, prefix + "T_after_C"] = T_after
    df.loc[mask, prefix + "deltaT_C"] = T_after - T_base
    
    ea_in = df.loc[mask, "ea_in_obs_kPa"]
    ea_out = df.loc[mask, "ea_out_kPa"]
    ea_after = (1.0 - vent_frac) * ea_in + vent_frac * ea_out
    df.loc[mask, prefix + "ea_after_kPa"] = ea_after
    
    es_after = sat_vapor_pressure_kpa(T_after)
    VPD_after = es_after - ea_after
    RH_after = (ea_after / es_after) * 100.0
    
    df.loc[mask, prefix + "VPD_kPa"] = VPD_after
    df.loc[mask, prefix + "RH_%"] = RH_after
    
    return df

# ================== 8. VPD 최적 제어 ==================
def suggest_low_energy_vpd_control(T_now, RH_now, VPD_target=1.5, floor_area_m2=400.0, height_m=4.0, T_cool_range_deg=5.0, verbose=True):
    VPD_now = calc_vpd_kPa(T_now, RH_now)
    es_now = sat_vapor_pressure_kpa(T_now)
    ea_now = es_now * RH_now / 100.0
    w_now = 0.622 * ea_now / (101.3 - ea_now)
    
    volume_m3 = floor_area_m2 * height_m
    m_air = 1.2 * volume_m3
    
    if VPD_now <= VPD_target + 0.05:
        return {"status": "already_ok", "VPD_now": VPD_now, "VPD_target": VPD_target}
    
    T_candidates = np.linspace(T_now, max(T_now - T_cool_range_deg, 10.0), 31)
    best = None
    
    for T_target in T_candidates:
        es_t = sat_vapor_pressure_kpa(T_target)
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
        Q_sens_kJ = m_air * 1.005 * dT
        q_sens_kWh_per_m2 = (Q_sens_kJ / 3600.0) / floor_area_m2
        
        delta_w = w_target - w_now
        m_H2O_kg = delta_w * m_air
        Q_lat_kJ = m_H2O_kg * 2450.0
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
        return {"status": "no_feasible_solution", "VPD_now": VPD_now, "VPD_target": VPD_target}
    
    best["status"] = "ok"
    best["VPD_now"] = float(VPD_now)
    return best

# ================== 메인 실행 ==================
if __name__ == "__main__":
    # 1. 지점 선택
    STN_ID = select_station_interactive()
    
    # 2. 데이터 병합
    df_final = merge_greenhouse_with_asos(STN_ID)
    
    if df_final is not None and not df_final.empty:
        # 3. 피복재/스크린 선택 (기본값 사용)
        cover_type = "pe_single"
        screen_type = "screen_50"
        
        # 4. 온실 파라미터 입력
        gh_floor_area = float(input("온실 바닥 면적 [m2] (기본 400): ") or 400.0)
        gh_height = float(input("온실 평균 높이 [m] (기본 4.0): ") or 4.0)
        U = float(input("피복 열관류율 U [W/m2K] (기본 6.0): ") or 6.0)
        ACH = float(input("자연환기 ACH [h-1] (기본 20.0): ") or 20.0)
        
        # 5. 차광 모델 계산
        df_with_shading = estimate_inside_temp_with_shading(
            df_final, cover_type, screen_type,
            gh_floor_area, gh_height, U, ACH
        )
        
        print("\n[차광스크린 적용 전/후 모델 온도 미리보기]")
        print(df_with_shading[[
            "datetime", "ext_temp",
            "T_in_model_noshade", "T_in_model_shaded", "deltaT_screen"
        ]].head().to_string(index=False))
        
        df_with_shading.to_csv(output_shading_path, index=False, encoding="utf-8-sig")
        print(f"[INFO] 차광스크린 효과 포함 데이터 CSV 저장 완료: {output_shading_path}")
        
        # 6. VPD 민감도 계산
        df_with_vpd = add_vpd_sensitivity_using_dewpoint(df_with_shading)
        df_with_vpd.to_csv(vpd_output_path, index=False, encoding="utf-8-sig")
        print(f"[INFO] VPD 민감도 포함 CSV 저장 완료: {vpd_output_path}")
        
        # 7. 환기 시뮬레이션
        angles = [0.0, 15.0, 30.0, 45.0]
        for ang in angles:
            prefix = f"vent_{int(ang)}deg_"
            df_with_shading = simulate_ventilation_effect_simple(
                df_with_shading, vent_angle_deg=ang,
                temp_base_col="T_in_model_shaded", prefix=prefix
            )
        
        df_with_shading.to_csv(vpd_vent_output, index=False, encoding="utf-8-sig")
        print(f"[INFO] 환기 효과 포함 CSV 저장 완료: {vpd_vent_output}")
        
        print("\n=== 실행 완료! 모든 CSV 파일이 현재 디렉토리에 저장되었습니다 ===")
        print(f"- {output_path}")
        print(f"- {output_shading_path}")
        print(f"- {vpd_output_path}")
        print(f"- {vpd_vent_output}")
