# outlier_find/find.py
import pandas as pd
import numpy as np
from scipy.stats import zscore
import os, json

SETTINGS_FILE = "config/settings.json"


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"h_location": 2, "r_location": 4, "t_location": 3}


def _robust_mad(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) == 0:
        return 0.0
    med = np.median(x)
    return np.median(np.abs(x - med))


def find_outliers_and_mark(df: pd.DataFrame, datetime_col: str = "time_str"):
    settings = load_settings()
    t_idx = settings.get("t_location", 3)
    h_idx = settings.get("h_location", 2)
    r_idx = settings.get("r_location", 4)

    cols = df.columns.tolist()
    temp_col = cols[t_idx]
    humi_col = cols[h_idx]
    light_col = cols[r_idx]

    dataset = df.copy()
    if datetime_col in dataset.columns:
        dataset[datetime_col] = pd.to_datetime(dataset[datetime_col], errors="coerce")
        dataset = dataset.set_index(datetime_col)
    else:
        dataset.index = pd.RangeIndex(len(dataset))

    # 숫자 변환
    for col in [temp_col, humi_col, light_col]:
        dataset[col] = pd.to_numeric(dataset[col], errors="coerce")

    temp = dataset[temp_col]
    hum = dataset[humi_col]
    light = dataset[light_col]

    # 0) 원래 NaN / Inf
    temp_nan_or_inf = temp.isna() | np.isinf(temp)
    hum_nan_or_inf = hum.isna() | np.isinf(hum)
    light_nan_or_inf = light.isna() | np.isinf(light)

    # ============================
    # 1. 온도/습도 이상치 (새 로직)
    # ============================
    TEMP_MIN, TEMP_MAX = -10, 50
    HUM_MIN, HUM_MAX = 0, 100

    # (1) 물리 범위
    temp_physical = (temp < TEMP_MIN) | (temp > TEMP_MAX)
    hum_physical = (hum < HUM_MIN) | (hum > HUM_MAX)

    # (2) 급변 (diff + z-score)
    diff_temp = temp.diff()
    diff_hum = hum.diff()
    z_temp = zscore(diff_temp, nan_policy="omit")
    z_hum = zscore(diff_hum, nan_policy="omit")
    Z_THRESH = 4

    cond_temp_diff = pd.Series(np.abs(z_temp) > Z_THRESH, index=temp.index).fillna(
        False
    )
    cond_hum_diff = pd.Series(np.abs(z_hum) > Z_THRESH, index=hum.index).fillna(False)

    # (3) 시간대별 문맥(3.5σ)
    if isinstance(dataset.index, pd.DatetimeIndex):
        time_key_temp = temp.index.time
        time_key_hum = hum.index.time
    else:
        # 시간 정보 없으면 전체 한 덩어리로 처리
        time_key_temp = pd.Index([0] * len(temp), name="time_of_day")
        time_key_hum = pd.Index([0] * len(hum), name="time_of_day")

    hourly_temp_stats = temp.groupby(time_key_temp).agg(
        median_temp="median", std_temp="std"
    )
    hourly_hum_stats = hum.groupby(time_key_hum).agg(
        median_hum="median", std_hum="std"
    )

    temp_with_ctx = temp.to_frame(name="temperature")
    temp_with_ctx["time_of_day"] = time_key_temp
    temp_with_ctx = temp_with_ctx.merge(
        hourly_temp_stats, left_on="time_of_day", right_index=True, how="left"
    )
    temp_with_ctx["upper_3_5sigma"] = (
        temp_with_ctx["median_temp"] + 3.5 * temp_with_ctx["std_temp"]
    )
    temp_with_ctx["lower_3_5sigma"] = (
        temp_with_ctx["median_temp"] - 3.5 * temp_with_ctx["std_temp"]
    )

    hum_with_ctx = hum.to_frame(name="humidity")
    hum_with_ctx["time_of_day"] = time_key_hum
    hum_with_ctx = hum_with_ctx.merge(
        hourly_hum_stats, left_on="time_of_day", right_index=True, how="left"
    )
    hum_with_ctx["upper_3_5sigma"] = (
        hum_with_ctx["median_hum"] + 3.5 * hum_with_ctx["std_hum"]
    )
    hum_with_ctx["lower_3_5sigma"] = (
        hum_with_ctx["median_hum"] - 3.5 * hum_with_ctx["std_hum"]
    ).clip(lower=0)

    anomaly_temp_ctx = (
        (temp_with_ctx["temperature"] > temp_with_ctx["upper_3_5sigma"])
        | (temp_with_ctx["temperature"] < temp_with_ctx["lower_3_5sigma"])
    ).fillna(False)

    anomaly_hum_ctx = (
        (hum_with_ctx["humidity"] > hum_with_ctx["upper_3_5sigma"])
        | (hum_with_ctx["humidity"] < hum_with_ctx["lower_3_5sigma"])
    ).fillna(False)

    # (4) 통합 이상치(all)
    all_anom_temp = (temp_physical | cond_temp_diff | anomaly_temp_ctx).fillna(False)
    all_anom_hum = (hum_physical | cond_hum_diff | anomaly_hum_ctx).fillna(False)

    # (5) 온도/습도 상관관계 기반 필터링
    combined = pd.DataFrame(
        {"temperature": temp, "humidity": hum, "time_of_day": time_key_temp}
    )
    hourly_corr = (
        combined.groupby("time_of_day")[["temperature", "humidity"]]
        .corr()
        .unstack()
        .iloc[:, 1]
    )  # temp-hum corr

    merged = temp_with_ctx[["temperature", "time_of_day", "median_temp"]].copy()
    merged["humidity"] = hum_with_ctx["humidity"]
    merged["median_hum"] = hum_with_ctx["median_hum"]
    merged["anom_temp_all"] = all_anom_temp
    merged["anom_hum_all"] = all_anom_hum
    merged = merged.merge(
        hourly_corr.rename("hourly_correlation"),
        left_on="time_of_day",
        right_index=True,
        how="left",
    )

    STRONG_CORR_TH = 0.5
    merged["sensor_error_candidate"] = False

    for idx, row in merged.iterrows():
        it = bool(row["anom_temp_all"])
        ih = bool(row["anom_hum_all"])
        corr = row["hourly_correlation"]

        if pd.isna(corr):
            continue

        # 한쪽만 이상 + 상관계수 큼 → 센서 오류 후보
        if (it != ih) and (abs(corr) > STRONG_CORR_TH):
            merged.at[idx, "sensor_error_candidate"] = True
        # 둘 다 이상인데 dev 방향이 상관관계와 안 맞으면 센서 오류
        elif it and ih:
            t_dev = row["temperature"] - row["median_temp"]
            h_dev = row["humidity"] - row["median_hum"]
            cons = True

            if corr < -STRONG_CORR_TH:
                # 음의 상관이면 서로 반대여야 정상
                cons = (t_dev * h_dev) < 0
            elif corr > STRONG_CORR_TH:
                # 양의 상관이면 같은 방향이어야 정상
                cons = (t_dev * h_dev) > 0
            else:
                cons = True  # 상관이 약하면 환경 변화로 간주

            if not cons:
                merged.at[idx, "sensor_error_candidate"] = True

    potential_temp = (all_anom_temp & merged["sensor_error_candidate"]).reindex(
        temp.index, fill_value=False
    )
    potential_hum = (all_anom_hum & merged["sensor_error_candidate"]).reindex(
        hum.index, fill_value=False
    )

    # 최종 센서 오류 마스크
    temp_fault_final = potential_temp.fillna(False)
    hum_fault_final = potential_hum.fillna(False)

    # ============================
    # 2. 광(일사량) 이상치 (새 로직, 단순화 버전)
    # ============================
    # 여기서는 PPFD 변환 없이, irradiance 자체를 사용하는 버전으로 단순화

    LIGHT_MIN = 0.0
    LIGHT_MAX = 3000.0

    # 물리 범위
    light_physical = (light < LIGHT_MIN) | (light > LIGHT_MAX)

    # 시간대/날씨 정보 없이, 시간대별 통계만 이용
    if isinstance(dataset.index, pd.DatetimeIndex):
        hour_key = dataset.index.hour
    else:
        hour_key = pd.Index([0] * len(light), name="hour")

    light_ctx = pd.DataFrame({"light": light, "hour": hour_key})
    # 시간대별 robust 통계
    stats = (
        light_ctx.groupby("hour")["light"]
        .agg(
            median_hour="median",
            p25_hour=lambda s: np.quantile(s.dropna(), 0.25)
            if s.notna().sum() > 0
            else np.nan,
            p75_hour=lambda s: np.quantile(s.dropna(), 0.75)
            if s.notna().sum() > 0
            else np.nan,
            mad_hour=_robust_mad,
        )
        .reset_index()
    )

    full_l = light_ctx.merge(stats, on="hour", how="left").set_index(light.index)

    iqr = (full_l["p75_hour"] - full_l["p25_hour"]).abs()
    IQR_LOWER_K, IQR_UPPER_K = 3.5, 6.0
    lower_bound = full_l["median_hour"] - IQR_LOWER_K * iqr
    upper_bound = full_l["median_hour"] + IQR_UPPER_K * iqr

    mask_iqr_lower = light < lower_bound
    mask_iqr_upper = light > upper_bound
    mask_iqr = (mask_iqr_lower | mask_iqr_upper).fillna(False)

    # MAD extreme
    mad = full_l["mad_hour"].replace(0, np.nan)
    robust_z = (light - full_l["median_hour"]).abs() / (mad + 1e-9)
    MAD_Z_UPPER = 20.0
    mask_mad_extreme = (robust_z > MAD_Z_UPPER).fillna(False)

    # 낮 시간대 저조도 (대략 9~16시)
    is_day = (hour_key >= 9) & (hour_key <= 16)
    PERCENTILE_LOW = 0.01
    q01 = (
        light_ctx.groupby("hour")["light"]
        .transform(lambda s: np.quantile(s.dropna(), PERCENTILE_LOW)
                   if s.notna().sum() > 0
                   else np.nan)
    )
    mask_day_low = ((light < q01) & is_day).fillna(False)

    # 급격한 변화
    diff_l = light.diff().fillna(0)
    mask_spike = (diff_l.abs() > 400).fillna(False)

    # 전체 후보
    candidate_light = (
        light_physical | mask_iqr | mask_mad_extreme | mask_day_low | mask_spike
    ).fillna(False)

    # 간단한 지속성 필터 (연속 구간 길이 기준)
    SAMPLE_MINUTES = 1
    MIN_DURATION_MINUTES = 5
    cand_int = candidate_light.astype(int)
    groups = (cand_int != cand_int.shift(1)).cumsum()
    seg_len = cand_int.groupby(groups).transform("sum")
    min_len_samples = max(1, int(MIN_DURATION_MINUTES / SAMPLE_MINUTES))
    persistent = (cand_int == 1) & (seg_len >= min_len_samples)

    # 환경 정상 mask: IQR/MAD 내 + 밤의 저조도 허용
    night_mask = (hour_key >= 18) | (hour_key <= 6)
    night_normal = (light <= 50) & night_mask
    context_normal = (~mask_iqr) & (~mask_mad_extreme)
    environment_mask = (context_normal | night_normal).fillna(False)

    final_light_fault = (persistent & ~environment_mask).fillna(False)

    # ============================
    # 3. NaN 마킹
    # ============================
    cleaned = dataset.copy()
    cleaned.loc[temp_fault_final, temp_col] = np.nan
    cleaned.loc[hum_fault_final, humi_col] = np.nan
    cleaned.loc[final_light_fault, light_col] = np.nan

    # ============================
    # 4. alarm_df 생성 (인터페이스 유지)
    # ============================
    records = []
    for ts in dataset.index:
        ts_str = (
            ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, pd.Timestamp) else str(ts)
        )

        temp_val = temp.loc[ts]
        hum_val = hum.loc[ts]
        light_val = light.loc[ts]

        # 온도
        if temp_fault_final.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "온도",
                    "value": float(temp_val) if pd.notna(temp_val) else None,
                    "status": "이상치",
                }
            )
        elif temp_nan_or_inf.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "온도",
                    "value": None,
                    "status": "결측치",
                }
            )

        # 습도
        if hum_fault_final.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "습도",
                    "value": float(hum_val) if pd.notna(hum_val) else None,
                    "status": "이상치",
                }
            )
        elif hum_nan_or_inf.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "습도",
                    "value": None,
                    "status": "결측치",
                }
            )

        # 광
        if final_light_fault.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "광",
                    "value": float(light_val) if pd.notna(light_val) else None,
                    "status": "이상치",
                }
            )
        elif light_nan_or_inf.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "광",
                    "value": None,
                    "status": "결측치",
                }
            )

    alarm_df = pd.DataFrame(records)

    # cleaned 정리 (원래 인터페이스 유지)
    cleaned = cleaned.reset_index()
    numeric_cols = [temp_col, humi_col, light_col]
    for col in numeric_cols:
        if col in cleaned.columns:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce").astype("float64")

    if datetime_col in cleaned.columns:
        cleaned[datetime_col] = pd.to_datetime(
            cleaned[datetime_col], errors="coerce"
        )

    return cleaned, alarm_df
