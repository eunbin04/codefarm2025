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

    # 숫자 변환 (Inf도 float로 남게 됨)
    for col in [temp_col, humi_col, light_col]:
        dataset[col] = pd.to_numeric(dataset[col], errors="coerce")

    temp = dataset[temp_col]
    hum = dataset[humi_col]
    light = dataset[light_col]

    # 0) 원래부터 NaN / Inf 여부 마스크
    temp_nan_or_inf = temp.isna() | np.isinf(temp)
    hum_nan_or_inf = hum.isna() | np.isinf(hum)
    light_nan_or_inf = light.isna() | np.isinf(light)

    # 1. 온도/습도 이상치
    TEMP_MIN, TEMP_MAX = -10, 40
    HUM_MIN, HUM_MAX = 0, 100

    temp_physical = (temp < TEMP_MIN) | (temp > TEMP_MAX)
    hum_physical = (hum < HUM_MIN) | (hum > HUM_MAX)

    diff_temp = temp.diff()
    diff_hum = hum.diff()

    z_temp = zscore(diff_temp, nan_policy="omit")
    z_hum = zscore(diff_hum, nan_policy="omit")
    Z = 4
    cond_temp_diff = pd.Series(np.abs(z_temp) > Z, index=dataset.index).fillna(False)
    cond_hum_diff = pd.Series(np.abs(z_hum) > Z, index=dataset.index).fillna(False)

    normal_env = ((diff_temp < 0) & (diff_hum > 0)) | ((diff_temp > 0) & (diff_hum < 0))
    normal_env = normal_env.fillna(False)

    cond_temp_diff_adj = cond_temp_diff & ~normal_env
    cond_hum_diff_adj = cond_hum_diff & ~normal_env

    temp_fault = (temp_physical | cond_temp_diff_adj).fillna(False)
    hum_fault = (hum_physical | cond_hum_diff_adj).fillna(False)

    # 2. 광 이상치
    LIGHT_MIN, LIGHT_MAX = 0, 1000
    LIGHT_UPPER_SUS = 10

    # 2-1. 물리 범위: 유한 값만
    light_physical = light.notna() & ~np.isinf(light) & (
        (light < LIGHT_MIN) | (light > LIGHT_MAX)
    )

    if isinstance(dataset.index, pd.DatetimeIndex):
        hourly_mean = light.groupby(dataset.index.hour).mean()
        hour = dataset.index.hour
        light_hourly_mean = pd.Series(hour, index=dataset.index).map(hourly_mean)
        MEAN_EPS = 0.05
        valid_hour = light_hourly_mean > MEAN_EPS

        finite_light = light.notna() & ~np.isinf(light)

        upper_ratio, lower_ratio = 1.7, 0.3
        light_too_high_rel = (
            valid_hour & finite_light & (light > light_hourly_mean * upper_ratio)
        )
        light_too_low_rel = (
            valid_hour & finite_light & (light < light_hourly_mean * lower_ratio)
        )
    else:
        light_too_high_rel = pd.Series(False, index=dataset.index)
        light_too_low_rel = pd.Series(False, index=dataset.index)

    # 2-2. 상한 의심: 유한 값만
    light_upper_sus = (~np.isinf(light)) & (light > LIGHT_UPPER_SUS)

    light_outlier = (
        light_physical | light_too_high_rel | light_too_low_rel | light_upper_sus
    ).fillna(False)


    # 3. NaN 마킹 (이상치로 판정된 위치를 NaN으로)
    cleaned = dataset.copy()
    cleaned.loc[temp_fault.values, temp_col] = np.nan
    cleaned.loc[hum_fault.values, humi_col] = np.nan
    cleaned.loc[light_outlier.values, light_col] = np.nan

    # 4. 센서별 알림 정보 생성 (이상치 + 결측치)
    records = []
    for ts in dataset.index:
        ts_str = (
            ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, pd.Timestamp) else str(ts)
        )

        temp_val = temp.loc[ts]
        hum_val = hum.loc[ts]
        light_val = light.loc[ts]

        # 온도
        if temp_fault.loc[ts]:
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
        if hum_fault.loc[ts]:
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
        if light_outlier.loc[ts]:
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "광",
                    "value": float(light_val) if pd.notna(light_val) else None,
                    "status": "이상치",
                }
            )
        elif light_nan_or_inf.loc[ts]:
            # NaN 또는 Inf 는 항상 결측치로
            records.append(
                {
                    "time_str": ts_str,
                    "alarm_type": "광",
                    "value": None,
                    "status": "결측치",
                }
            )

    alarm_df = pd.DataFrame(records)

    # cleaned 정리
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
