import pandas as pd
import numpy as np
import requests
import json
import os

from vpd_model import (
    estimate_inside_temp_with_shading,
    add_inside_radiation_model,
    add_vpd_for_shading,
    compute_enthalpy_and_abs_humidity,
    compute_ventilation_humidity_removal,
    compute_three_stage_vpd,
    suggest_low_energy_vpd_control,
    DEFAULT_ATM_PRESS_KPA,
)

from app_details.alarms_db import (
    initialize_alarms_db,
    save_vpd_solution_alarm,
)

STATION_DIR = "data/station_code.csv"
GROWTH_CSV_PATH = "data/mc_3m.csv"
ASOS_URL = "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"
SETTINGS_FILE = "config/settings.json"


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {SETTINGS_FILE}")
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        s = json.load(f)
    return {
        "station_id": str(s.get("station_id")),
        "facility_key": s.get("facility_key", "glass_venlo"),
        "cover_type": s.get("cover_type", "film_PE"),
        "vent_angle_deg": float(s.get("vent_angle_deg", 30.0)),
        "gh_height": float(s.get("gh_height", 4.5)),
    }


def make_greenhouse_10min(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    df["datetime"] = pd.to_datetime(
        df["date_time"].str.replace(" T ", " "),
        errors="coerce"
    )
    df = df.set_index("datetime").sort_index()
    num_cols = df.select_dtypes(include=[np.number]).columns
    df_10min = df[num_cols].resample("10min").mean()
    if "light" in df_10min.columns:
        from vpd_model import LUX_TO_WM2
        df_10min["light_lux"] = df_10min["light"]
        df_10min["light_Wm2"] = df_10min["light"] * LUX_TO_WM2
    df_10min = df_10min.reset_index()
    return df_10min


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
            body = data.get("response", {}).get("body", {})
            items_obj = body.get("items")
            if items_obj is None:
                print("[ASOS] items 가 없습니다. 구조 확인 필요.")
                items = []
            else:
                items = items_obj.get("item", [])
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


def merge_greenhouse_asos(df_gh10: pd.DataFrame,
                          df_asos10: pd.DataFrame) -> pd.DataFrame:
    df_gh = df_gh10.set_index("datetime").sort_index()
    df_as = df_asos10.set_index("datetime").sort_index()
    df_merged = df_gh.join(df_as, how="left")
    df_merged = df_merged.reset_index()
    return df_merged


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


def main():
    # VPD 솔루션도 alarms.db를 쓰므로 초기화
    initialize_alarms_db()

    settings = load_settings()
    STN_ID = settings["station_id"]
    facility_key = settings["facility_key"]
    cover_type = settings["cover_type"]
    vent_angle = settings["vent_angle_deg"]
    gh_height = settings["gh_height"]
    gh_floor_area = 1.0
    screen_type = "screen_50"

    df_gh10 = make_greenhouse_10min(GROWTH_CSV_PATH)
    print("[GH] 온실 10분 평균 데이터 범위:",
          df_gh10["datetime"].min(), "~", df_gh10["datetime"].max())

    gh_start = df_gh10["datetime"].min()
    gh_end = df_gh10["datetime"].max()

    df_asos_hourly = fetch_asos_hourly(
        stn_id=STN_ID,
        start_dt=gh_start.floor("H"),
        end_dt=gh_end.ceil("H"),
        service_key=SERVICE_KEY,
        max_requests=5,
    )
    df_asos10 = make_asos_10min(df_asos_hourly, gh_start, gh_end)

    df_merged = merge_greenhouse_asos(df_gh10, df_asos10)
    df_merged["vent_angle_deg"] = vent_angle

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

    # 대표 시점 선택 + VPD 솔루션 DB 저장
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

        # CSV 요약 저장(기존)
        control_csv_path = "vpd_control_solution_summary_per_m2_three_stage.csv"
        vpd_col_sel = "VPD_stage2" if not pd.isna(sel_row["VPD_stage2"]) else None
        save_control_solution_to_csv(sel_row, best, vpd_col_sel, control_csv_path)

        # === VPD 솔루션 알림 DB 저장 (시간, VPD, 온도, 습도, 전략 요약/상세) ===
        time_str = str(sel_row.get("datetime"))
        vpd_now = float(sel_row.get("VPD_stage2", np.nan))
        T_now = float(sel_row.get("T_stage2", np.nan))
        RH_now = float(sel_row.get("RH_stage2", np.nan))

        solution_summary = (
            f"T={best['T_target']:.1f}°C, RH={best['RH_target']:.1f}%, "
            f"ΔT={best['cooling_dT_C']:.1f}°C, "
            f"q_tot={best['q_tot_kWh_per_m2']:.3f} kWh/m²"
        )

        solution_detail = {
            "T_target": best.get("T_target"),
            "RH_target": best.get("RH_target"),
            "cooling_dT_C": best.get("cooling_dT_C"),
            "water_L_per_m2": best.get("water_L_per_m2"),
            "water_L_total": best.get("water_L_total"),
            "q_sens_kWh_per_m2": best.get("q_sens_kWh_per_m2"),
            "q_lat_kWh_per_m2": best.get("q_lat_kWh_per_m2"),
            "q_tot_kWh_per_m2": best.get("q_tot_kWh_per_m2"),
        }

        save_vpd_solution_alarm(
            time_str=time_str,
            vpd=vpd_now,
            temperature=T_now,
            humidity=RH_now,
            solution_summary=solution_summary,
            solution_detail=solution_detail,
        )


if __name__ == "__main__":
    main()
