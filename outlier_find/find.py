# outlier_find/find.py
import os
import json
import numpy as np
import pandas as pd
from scipy.stats import zscore
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings("ignore")

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


def _safe_time(idx):
    if isinstance(idx, pd.DatetimeIndex):
        return idx.time
    else:
        start_time = pd.Timestamp("2025-01-01")
        fake_times = pd.date_range(start_time, periods=len(idx), freq="1min")
        return fake_times.time


def _safe_hour(idx):
    if isinstance(idx, pd.DatetimeIndex):
        return idx.hour
    else:
        return np.arange(len(idx)) % 24


def find_outliers_and_mark(df: pd.DataFrame, datetime_col: str = "time_str"):
    # ============================
    # 0. 기본 준비
    # ============================
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
        dataset[datetime_col] = pd.to_datetime(
            dataset[datetime_col], errors="coerce"
        )
        dataset = dataset.dropna(subset=[datetime_col])
        dataset = dataset.set_index(datetime_col).sort_index()
        dataset = dataset[~dataset.index.duplicated(keep="first")]
    else:
        dataset.index = pd.RangeIndex(len(dataset))

    for col in [temp_col, humi_col, light_col]:
        dataset[col] = pd.to_numeric(dataset[col], errors="coerce")

    temp = dataset[temp_col]
    hum = dataset[humi_col]
    light = dataset[light_col]

    # 0) 원래 NaN / Inf
    temp_nan_or_inf = temp.isna() | np.isinf(temp)
    hum_nan_or_inf = hum.isna() | np.isinf(hum)
    light_nan_or_inf = light.isna() | np.isinf(light)

    # ============================================================
    # 1. 온도/습도 이상치 탐지 (풀 버전)
    # ============================================================
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

    cond_temp_diff = pd.Series(
        np.abs(z_temp) > Z_THRESH, index=temp.index
    ).fillna(False)
    cond_hum_diff = pd.Series(
        np.abs(z_hum) > Z_THRESH, index=hum.index
    ).fillna(False)

    # (3) 시간대별 문맥(3.5σ)
    time_key_temp = _safe_time(temp.index)
    time_key_hum = _safe_time(hum.index)

    # NaN 제거 후 시간대 통계
    temp_nonan = temp.dropna()
    hum_nonan = hum.dropna()

    hourly_temp_stats = temp_nonan.groupby(_safe_time(temp_nonan.index)).agg(
        median_temp="median", std_temp="std"
    )
    hourly_hum_stats = hum_nonan.groupby(_safe_time(hum_nonan.index)).agg(
        median_hum="median", std_hum="std"
    )

    temp_with_ctx = temp.to_frame(name="temperature")
    temp_with_ctx["time_of_day"] = _safe_time(temp_with_ctx.index)
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
    hum_with_ctx["time_of_day"] = _safe_time(hum_with_ctx.index)
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
    all_anom_temp = (
        temp_physical | cond_temp_diff | anomaly_temp_ctx
    ).reindex(temp.index, fill_value=False)
    all_anom_hum = (
        hum_physical | cond_hum_diff | anomaly_hum_ctx
    ).reindex(hum.index, fill_value=False)

    # (5) 온도/습도 상관관계 기반 필터링
    combined = pd.DataFrame(
        {
            "temperature": temp,
            "humidity": hum,
            "time_of_day": _safe_time(dataset.index),
        }
    )
    hourly_corr = (
        combined.dropna(subset=["temperature", "humidity"])
        .groupby("time_of_day")[["temperature", "humidity"]]
        .corr()
        .unstack()
        .iloc[:, 1]
    )

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

        if (it != ih) and (abs(corr) > STRONG_CORR_TH):
            merged.at[idx, "sensor_error_candidate"] = True
        elif it and ih:
            t_dev = row["temperature"] - row["median_temp"]
            h_dev = row["humidity"] - row["median_hum"]
            cons = True

            if corr < -STRONG_CORR_TH:
                cons = (t_dev * h_dev) < 0
            elif corr > STRONG_CORR_TH:
                cons = (t_dev * h_dev) > 0
            else:
                cons = True

            if not cons:
                merged.at[idx, "sensor_error_candidate"] = True

    potential_temp = (all_anom_temp & merged["sensor_error_candidate"]).reindex(
        temp.index, fill_value=False
    )
    potential_hum = (all_anom_hum & merged["sensor_error_candidate"]).reindex(
        hum.index, fill_value=False
    )

    temp_fault_final = potential_temp.fillna(False)
    hum_fault_final = potential_hum.fillna(False)

    # ============================================================
    # 2. 조도(PPFD) 이상치 탐지 - 확장 버전 (weather_state + cloud)
    # ============================================================
    ld = light.copy()

    # weather_state 생성 (일별 max/mean/std/median 기반 KMeans)
    if "weather_state" not in dataset.columns:
        if isinstance(dataset.index, pd.DatetimeIndex):
            daily = ld.resample("D").agg(["max", "mean", "std", "median"]).dropna()
        else:
            fake_dates = pd.date_range(
                "2025-01-01", periods=len(ld), freq="1min"
            )
            ld_fake = ld.copy()
            ld_fake.index = fake_dates
            daily = ld_fake.resample("D").agg(["max", "mean", "std", "median"]).dropna()

        if len(daily) >= 3:
            scaler = StandardScaler()
            df_s = scaler.fit_transform(daily)
            kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
            daily["cluster"] = kmeans.fit_predict(df_s)
            mean_order = (
                daily.groupby("cluster")["mean"]
                .mean()
                .sort_values(ascending=False)
                .index
            )
            mapping = {
                mean_order[0]: "clear",
                mean_order[1]: "cloudy",
                mean_order[2]: "very cloudy",
            }
            daily["weather_state"] = daily["cluster"].map(mapping)
        else:
            daily["weather_state"] = "clear"

        dataset["weather_state"] = daily["weather_state"].reindex(
            dataset.index, method="ffill"
        )

    SAMPLE_MINUTES = 1
    MIN_DURATION_MINUTES = 5
    IQR_LOWER_K = 3.5
    IQR_UPPER_K = 6.0
    MAD_Z_UPPER = 20.0
    PERCENTILE_LOW = 0.01
    CLOUD_DROP_PERC = 0.4
    CLOUD_RECOVER_PERC = 0.3
    CLOUD_RECOVER_WINDOW = 10

    light_ctx = (
        dataset[[light_col, "weather_state"]]
        .dropna()
        .rename(columns={light_col: "light"})
    )

    hourly_stats = (
        light_ctx.groupby(
            [
                pd.Series(_safe_hour(light_ctx.index), index=light_ctx.index).rename(
                    "hour"
                ),
                "weather_state",
            ]
        )
        .agg(
            median_hour=("light", "median"),
            mad_hour=("light", _robust_mad),
            q01_hour=("light", lambda s: np.quantile(s, PERCENTILE_LOW)),
            q99_hour=("light", lambda s: np.quantile(s, 0.99)),
            p25_hour=("light", lambda s: np.quantile(s, 0.25)),
            p75_hour=("light", lambda s: np.quantile(s, 0.75)),
            count_hour=("light", "size"),
        )
        .reset_index()
    )

    full = (
        dataset[[light_col, "weather_state"]]
        .copy()
        .rename(columns={light_col: "light"})
    )
    full["hour"] = _safe_hour(full.index)

    idx_name = dataset.index.name if dataset.index.name is not None else "index"
    full = (
        full.reset_index()
        .merge(hourly_stats, on=["hour", "weather_state"], how="left")
        .set_index(idx_name)
    )

    full["light"] = ld.reindex(full.index)

    # 물리 범위
    LIGHT_PPFD_MIN = 0.0
    LIGHT_PPFD_MAX = 3000.0
    mask_physical = (full["light"] < LIGHT_PPFD_MIN) | (full["light"] > LIGHT_PPFD_MAX)

    iqr = (full["p75_hour"] - full["p25_hour"]).abs()
    lower_bound = full["median_hour"] - IQR_LOWER_K * iqr
    upper_bound = full["median_hour"] + IQR_UPPER_K * iqr
    mask_iqr_lower = full["light"] < lower_bound
    mask_iqr_upper = full["light"] > upper_bound
    mask_iqr = (mask_iqr_lower | mask_iqr_upper).fillna(False)

    mad = full["mad_hour"].replace(0, np.nan)
    robust_z = (full["light"] - full["median_hour"]).abs() / (mad + 1e-9)
    mask_mad_extreme = (robust_z > MAD_Z_UPPER).fillna(False)

    is_day = (full["hour"] >= 9) & (full["hour"] <= 16)
    mask_day_low = ((full["light"] < full["q01_hour"]) & is_day).fillna(False)

    diff_light = full["light"].diff().fillna(0)
    mask_spike = (diff_light.abs() > 400).fillna(False)

    # 구름 패턴
    prev = full["light"].shift(1)
    drop_mask = (full["light"] <= prev * (1 - CLOUD_DROP_PERC))
    recovery_mask = pd.Series(False, index=full.index)
    for i in range(len(full)):
        if i + CLOUD_RECOVER_WINDOW < len(full):
            if (
                i > 0
                and full["light"].iat[i]
                <= full["light"].iat[i - 1] * (1 - CLOUD_DROP_PERC)
            ):
                after_max = full["light"].iloc[i + 1 : i + 1 + CLOUD_RECOVER_WINDOW].max()
                if after_max >= full["light"].iat[i - 1] * (1 - CLOUD_DROP_PERC) * (
                    1 + CLOUD_RECOVER_PERC
                ):
                    recovery_mask.iat[i] = True
    mask_cloud = (drop_mask & recovery_mask).fillna(False)

    candidate = (
        mask_physical
        | mask_iqr
        | mask_mad_extreme
        | mask_spike
        | mask_day_low
    ).fillna(False)

    cand_int = candidate.astype(int)
    groups = (cand_int != cand_int.shift(1)).cumsum()
    seg_len = cand_int.groupby(groups).transform("sum")
    min_len_samples = max(1, int(MIN_DURATION_MINUTES / SAMPLE_MINUTES))
    persistent = (cand_int == 1) & (seg_len >= min_len_samples)

    context_normal = (~mask_iqr) & (~mask_mad_extreme)
    night_mask = (full["hour"] >= 18) | (full["hour"] <= 6)
    night_normal = (full["light"] <= 50) & night_mask
    environment_mask = (context_normal | night_normal | mask_cloud).fillna(False)

    final_faults = (persistent & (~environment_mask)).fillna(False)
    light_fault = final_faults.reindex(dataset.index, fill_value=False)

    # ============================================================
    # 3. NaN 마킹
    # ============================================================
    cleaned = dataset.copy()
    cleaned.loc[temp_fault_final, temp_col] = np.nan
    cleaned.loc[hum_fault_final, humi_col] = np.nan
    cleaned.loc[light_fault, light_col] = np.nan

    if "weather_state" in cleaned.columns:
        cleaned = cleaned.drop(columns=["weather_state"])

    # ============================================================
    # 4. alarm_df 생성 (인터페이스 유지)
    # ============================================================
    records = []
    for ts in dataset.index:
        ts_str = (
            ts.strftime("%Y-%m-%d %H:%M")
            if isinstance(ts, pd.Timestamp)
            else str(ts)
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
        if light_fault.loc[ts]:
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

    cleaned = cleaned.reset_index()
    numeric_cols = [temp_col, humi_col, light_col]
    for col in numeric_cols:
        if col in cleaned.columns:
            cleaned[col] = (
                pd.to_numeric(cleaned[col], errors="coerce").astype("float64")
            )

    if datetime_col in cleaned.columns:
        cleaned[datetime_col] = pd.to_datetime(
            cleaned[datetime_col], errors="coerce"
        )

    return cleaned, alarm_df
