# find_outlier.py
import os
import pandas as pd
import numpy as np
from scipy.stats import zscore


def find_outlier(file_path, output_path=None, location_map=None):
    if location_map is None:
        location_map = {
            0: 'date_time',
            1: 'Temperature',
            3: 'Humidity',
            4: 'Light'
        }
    location_map = {k: v for k, v in location_map.items() if k is not None}

    sorted_items = sorted(location_map.items(), key=lambda x: x[0])
    use_cols = [idx for idx, _ in sorted_items]
    col_names = [name for _, name in sorted_items]

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    dir_name = os.path.dirname(file_path)

    if output_path is None:
        output_dir = os.path.join(dir_name, "outliers")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{base_name}_delete_error.csv")
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # --- 원본 백업 파일 경로 생성 ---
    backup_path = os.path.join(dir_name, f"{base_name}_original_backup.csv")

    # --- 1. 원본 읽기 (백업용) ---
    raw = pd.read_csv(file_path)
    
    # --- 2. 원본 백업 저장 ---
    raw.to_csv(backup_path, index=False, encoding='utf-8-sig')
    print(f"📦 원본 데이터 백업 파일 저장 완료: {backup_path}")

    # --- 3. 백업 파일에서 분석용 데이터 읽기 ---
    dataset = pd.read_csv(backup_path, usecols=use_cols)
    dataset.columns = col_names

    if 'date_time' in dataset.columns:
        dataset['date_time'] = pd.to_datetime(dataset['date_time'])
        dataset = dataset.set_index('date_time')

    for col in ['Temperature', 'Humidity', 'Light']:
        if col in dataset.columns:
            dataset[col] = pd.to_numeric(dataset[col], errors='coerce')

    temp = dataset['Temperature'] if 'Temperature' in dataset.columns else pd.Series(index=dataset.index, dtype='float')
    hum = dataset['Humidity'] if 'Humidity' in dataset.columns else pd.Series(index=dataset.index, dtype='float')
    light = dataset['Light'] if 'Light' in dataset.columns else pd.Series(index=dataset.index, dtype='float')


    # 2. 이상치 탐지
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

    LIGHT_MIN, LIGHT_MAX = 0, 20000
    LIGHT_UPPER_SUS = 5400

    light_physical = (light < LIGHT_MIN) | (light > LIGHT_MAX)

    hourly_mean = light.groupby(light.index.hour).mean()
    hour = dataset.index.hour
    light_hourly_mean = pd.Series(hour, index=dataset.index).map(hourly_mean)

    MEAN_EPS = 50
    upper_ratio = 1.7
    lower_ratio = 0.3

    valid_hour = light_hourly_mean > MEAN_EPS

    light_too_high_rel = valid_hour & (light > light_hourly_mean * upper_ratio)
    light_too_low_rel = valid_hour & (light < light_hourly_mean * lower_ratio)

    light_upper5400 = light > LIGHT_UPPER_SUS

    light_outlier = (light_physical | light_too_high_rel | light_too_low_rel | light_upper5400).fillna(False)

    cleaned = raw.copy()

    if 'Temperature' in cleaned.columns:
        cleaned.loc[temp_fault.values, 'Temperature'] = np.nan
    if 'Humidity' in cleaned.columns:
        cleaned.loc[hum_fault.values, 'Humidity'] = np.nan
    if 'Light' in cleaned.columns:
        cleaned.loc[light_outlier.values, 'Light'] = np.nan

    cleaned.to_csv(output_path, index=False, encoding='utf-8-sig')

    print(f"최종 오류 구간 빈칸 처리 CSV 저장 완료: {output_path}")

    return output_path

if __name__ == "__main__":
    # 예시 실행용 기본값
    find_outlier('data/priva.csv')
