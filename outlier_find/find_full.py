# outlier_find/find_outlier.py
import pandas as pd
import numpy as np
from scipy.stats import zscore

def find_outlier_df(df, temp_index, humi_index, light_index):
    cols = df.columns.tolist()
    temp_col = cols[temp_index]
    humi_col = cols[humi_index]
    light_col = cols[light_index]

    dataset = df.copy()
    if 'date_time' in dataset.columns:
        dataset['date_time'] = pd.to_datetime(dataset['date_time'])
        dataset = dataset.set_index('date_time')
    else:
        # 임의 인덱스 사용 (불리면 보정로직이 바뀔 수 있음)
        dataset.index = pd.RangeIndex(len(dataset))

    for col in [temp_col, humi_col, light_col]:
        dataset[col] = pd.to_numeric(dataset[col], errors='coerce')

    temp = dataset[temp_col]
    hum = dataset[humi_col]
    light = dataset[light_col]

    # 1. 온도/습도 이상치 탐지
    TEMP_MIN, TEMP_MAX = -10, 40
    HUM_MIN, HUM_MAX = 0, 100

    temp_physical = (temp < TEMP_MIN) | (temp > TEMP_MAX)
    hum_physical = (hum < HUM_MIN) | (hum > HUM_MAX)

    diff_temp = temp.diff()
    diff_hum = hum.diff()

    z_temp = zscore(diff_temp, nan_policy='omit')
    z_hum = zscore(diff_hum, nan_policy='omit')

    Z_THRESH = 4
    cond_temp_diff = pd.Series(np.abs(z_temp) > Z_THRESH, index=dataset.index).fillna(False)
    cond_hum_diff = pd.Series(np.abs(z_hum) > Z_THRESH, index=dataset.index).fillna(False)

    normal_env = ((diff_temp < 0) & (diff_hum > 0)) | ((diff_temp > 0) & (diff_hum < 0))
    normal_env = normal_env.fillna(False)

    cond_temp_diff_adj = cond_temp_diff & ~normal_env
    cond_hum_diff_adj = cond_hum_diff & ~normal_env

    temp_fault = (temp_physical | cond_temp_diff_adj).fillna(False)
    hum_fault = (hum_physical | cond_hum_diff_adj).fillna(False)

    # 2. 광 이상치 탐지
    LIGHT_MIN, LIGHT_MAX = 0, 20000
    LIGHT_UPPER_SUS = 5400

    light_physical = (light < LIGHT_MIN) | (light > LIGHT_MAX)
    if 'date_time' in df.columns:
        hourly_mean = light.groupby(dataset.index.hour).mean()
        hour = dataset.index.hour
        light_hourly_mean = pd.Series(hour, index=dataset.index).map(hourly_mean)
        valid_hour = light_hourly_mean > 50
        upper_ratio = 1.7
        lower_ratio = 0.3
        light_too_high_rel = valid_hour & (light > light_hourly_mean * upper_ratio)
        light_too_low_rel = valid_hour & (light < light_hourly_mean * lower_ratio)
    else:
        # 시간별 평균 불가 시 단순 값
        light_too_high_rel = pd.Series(False, index=dataset.index)
        light_too_low_rel = pd.Series(False, index=dataset.index)
    light_upper5400 = light > LIGHT_UPPER_SUS

    light_outlier = (light_physical | light_too_high_rel | light_too_low_rel | light_upper5400).fillna(False)

    # 3. NaN 마킹 처리
    dataset.loc[temp_fault.values, temp_col] = np.nan
    dataset.loc[hum_fault.values, humi_col] = np.nan
    dataset.loc[light_outlier.values, light_col] = np.nan

    # 인덱스를 복구 (다운로드를 위해)
    dataset = dataset.reset_index()
    return dataset

# (아래는 모듈 실행용 샘플, 실제 서비스에서는 사용 안함)
if __name__ == "__main__":
    df = pd.read_csv("sample.csv")
    result = find_outlier_df(df, 1, 2, 3)
    print(result.tail())
