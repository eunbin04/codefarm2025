# outlier_find/find_full.py
import pandas as pd
import numpy as np
from scipy.stats import zscore
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings('ignore')

def robust_mad(x):
    return np.median(np.abs(x - np.median(x)))

def safe_time_extract(idx):
    """🔴 안전한 시간 추출 (RangeIndex/DatetimeIndex 모두 지원)"""
    if isinstance(idx, pd.DatetimeIndex):
        return idx.time
    else:
        # RangeIndex → 00:00부터 1분 간격 가상 시간
        start_time = pd.Timestamp('2025-01-01')
        fake_times = pd.date_range(start_time, periods=len(idx), freq='1min')
        return fake_times.time

def safe_hour_extract(idx):
    """🔴 안전한 시간(시) 추출"""
    if isinstance(idx, pd.DatetimeIndex):
        return idx.hour
    else:
        return np.arange(len(idx)) % 24  # 0-23 순환

def find_outlier_df(df, temp_index, humi_index, light_index, timestamp_index=None):
    """timestamp_index 우선 사용 → 항상 안전한 시간 처리"""
    cols = df.columns.tolist()
    temp_col = cols[temp_index]
    humi_col = cols[humi_index]
    light_col = cols[light_index]
    
    dataset = df.copy()
    
    # 🔴 타임스탬프 기반 인덱스 설정 (단일 로직)
    if timestamp_index is not None and cols[timestamp_index] in dataset.columns:
        timestamp_col = cols[timestamp_index]
        dataset[timestamp_col] = pd.to_datetime(dataset[timestamp_col], errors='coerce')
        dataset = dataset.dropna(subset=[timestamp_col])
        dataset = dataset.set_index(timestamp_col).sort_index()
        dataset = dataset[~dataset.index.duplicated(keep='first')]
    elif 'date_time' in dataset.columns:
        dataset['date_time'] = pd.to_datetime(dataset['date_time'], errors='coerce')
        dataset = dataset.dropna(subset=['date_time'])
        dataset = dataset.set_index('date_time').sort_index()
        dataset = dataset[~dataset.index.duplicated(keep='first')]
    else:
        dataset.index = pd.RangeIndex(len(dataset))

    # 숫자형 변환
    for col in [temp_col, humi_col, light_col]:
        dataset[col] = pd.to_numeric(dataset[col], errors='coerce')

    temp = dataset[temp_col]
    hum = dataset[humi_col]
    light = dataset[light_col]

    # ============================================================
    # A. 온도 / 습도 이상치 탐지
    # ============================================================

    # (1) 물리적 범위
    TEMP_MIN, TEMP_MAX = -10, 50
    HUM_MIN, HUM_MAX = 0, 100

    temp_physical = (temp < TEMP_MIN) | (temp > TEMP_MAX)
    hum_physical = (hum < HUM_MIN) | (hum > HUM_MAX)

    # (2) diff + z-score 급변
    diff_temp = temp.diff()
    diff_hum = hum.diff()
    z_temp = zscore(diff_temp, nan_policy='omit')
    z_hum = zscore(diff_hum, nan_policy='omit')
    Z_THRESH = 4

    cond_temp_diff = pd.Series(np.abs(z_temp) > Z_THRESH,
                              index=temp.index).fillna(False)
    cond_hum_diff = pd.Series(np.abs(z_hum) > Z_THRESH,
                              index=hum.index).fillna(False)

    # (3) 시간대별(시각 기준) 문맥 3.5σ 밴드 (🔴 안전 수정)
    temp_nonan = temp.dropna()
    hum_nonan = hum.dropna()
    
    hourly_temp_stats = temp_nonan.groupby(safe_time_extract(temp_nonan.index)).agg(
        median_temp='median', std_temp='std'
    )
    hourly_hum_stats = hum_nonan.groupby(safe_time_extract(hum_nonan.index)).agg(
        median_hum='median', std_hum='std'
    )

    # 전체 데이터로 시간대 문맥 계산
    temp_all = temp.to_frame(name='temperature')
    temp_all['time_of_day'] = safe_time_extract(temp_all.index)  # 🔴 안전
    temp_all = temp_all.merge(
        hourly_temp_stats,
        left_on='time_of_day',
        right_index=True,
        how='left'
    )
    temp_all['upper_3_5sigma'] = (
        temp_all['median_temp'] + 3.5 * temp_all['std_temp']
    )
    temp_all['lower_3_5sigma'] = (
        temp_all['median_temp'] - 3.5 * temp_all['std_temp']
    )

    anomaly_temp_ctx = (
        (temp_all['temperature'] > temp_all['upper_3_5sigma']) |
        (temp_all['temperature'] < temp_all['lower_3_5sigma'])
    ).fillna(False)

    # 습도도 동일하게
    hum_all = hum.to_frame(name='humidity')
    hum_all['time_of_day'] = safe_time_extract(hum_all.index)  # 🔴 안전
    hum_all = hum_all.merge(
        hourly_hum_stats,
        left_on='time_of_day',
        right_index=True,
        how='left'
    )
    hum_all['upper_3_5sigma'] = (
        hum_all['median_hum'] + 3.5 * hum_all['std_hum']
    )
    hum_all['lower_3_5sigma'] = (
        hum_all['median_hum'] - 3.5 * hum_all['std_hum']
    ).clip(lower=0)

    anomaly_hum_ctx = (
        (hum_all['humidity'] > hum_all['upper_3_5sigma']) |
        (hum_all['humidity'] < hum_all['lower_3_5sigma'])
    ).fillna(False)

    # 인덱스 재정렬
    temp_physical_ds = temp_physical.reindex(dataset.index, fill_value=False)
    hum_physical_ds = hum_physical.reindex(dataset.index, fill_value=False)
    cond_temp_diff_ds = cond_temp_diff.reindex(dataset.index, fill_value=False)
    cond_hum_diff_ds = cond_hum_diff.reindex(dataset.index, fill_value=False)
    anomaly_temp_ctx_ds = anomaly_temp_ctx.reindex(dataset.index, fill_value=False)
    anomaly_hum_ctx_ds = anomaly_hum_ctx.reindex(dataset.index, fill_value=False)

    # 통합 초기 이상치
    all_anom_temp = (temp_physical_ds |
                     cond_temp_diff_ds |
                     anomaly_temp_ctx_ds)
    all_anom_hum = (hum_physical_ds |
                    cond_hum_diff_ds |
                    anomaly_hum_ctx_ds)

    # (4) 시간대별 온도–습도 상관관계 기반 센서 오류 필터 (🔴 안전 수정)
    combined = dataset[[temp_col, humi_col]].copy()
    combined.columns = ['temperature', 'humidity']
    combined['time_of_day'] = safe_time_extract(combined.index)  # 🔴 안전

    hourly_corr = (
        combined
        .dropna(subset=['temperature', 'humidity'])
        .groupby('time_of_day')[['temperature', 'humidity']]
        .corr()
        .unstack()
        .iloc[:, 1]
    )

    merged_anom = temp_all[['temperature', 'time_of_day', 'median_temp']].copy()
    merged_anom['humidity'] = hum_all['humidity']
    merged_anom['median_hum'] = hum_all['median_hum']
    merged_anom['anomaly_temp_total'] = all_anom_temp.reindex(merged_anom.index, fill_value=False)
    merged_anom['anomaly_hum_total'] = all_anom_hum.reindex(merged_anom.index, fill_value=False)
    merged_anom = merged_anom.merge(
        hourly_corr.rename('hourly_correlation'),
        left_on='time_of_day',
        right_index=True,
        how='left'
    )

    STRONG_CORR_TH = 0.5
    merged_anom['sensor_error_candidate'] = False

    for idx, row in merged_anom.iterrows():
        is_temp_anom = row['anomaly_temp_total']
        is_hum_anom = row['anomaly_hum_total']
        corr_val = row['hourly_correlation']

        if pd.isna(corr_val):
            continue

        if (is_temp_anom != is_hum_anom) and (abs(corr_val) > STRONG_CORR_TH):
            merged_anom.at[idx, 'sensor_error_candidate'] = True
        elif is_temp_anom and is_hum_anom:
            temp_dev = row['temperature'] - row['median_temp']
            hum_dev = row['humidity'] - row['median_hum']
            is_consistent = False

            if corr_val < -STRONG_CORR_TH:
                if (temp_dev * hum_dev) < 0:
                    is_consistent = True
            elif corr_val > STRONG_CORR_TH:
                if (temp_dev * hum_dev) > 0:
                    is_consistent = True
            else:
                is_consistent = True

            if not is_consistent:
                merged_anom.at[idx, 'sensor_error_candidate'] = True

    sensor_err_temp = all_anom_temp & merged_anom['sensor_error_candidate'].reindex(
        all_anom_temp.index, fill_value=False
    )
    sensor_err_hum = all_anom_hum & merged_anom['sensor_error_candidate'].reindex(
        all_anom_hum.index, fill_value=False
    )

    temp_fault = sensor_err_temp.fillna(False)
    hum_fault = sensor_err_hum.fillna(False)

    # ============================================================
    # B. 조도(PPFD) 이상치 탐지 (🔴 안전 수정)
    # ============================================================

    ld = light

    # weather_state 생성
    if 'weather_state' not in dataset.columns:
        if isinstance(dataset.index, pd.DatetimeIndex):
            daily = ld.resample('D').agg(['max', 'mean', 'std', 'median']).dropna()
        else:
            # RangeIndex용 가상 날짜
            fake_dates = pd.date_range('2025-01-01', periods=len(ld), freq='1min')
            ld_fake = ld.copy()
            ld_fake.index = fake_dates
            daily = ld_fake.resample('D').agg(['max', 'mean', 'std', 'median']).dropna()
        
        if len(daily) >= 3:
            scaler = StandardScaler()
            df_s = scaler.fit_transform(daily)
            kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
            daily['cluster'] = kmeans.fit_predict(df_s)
            mean_order = daily.groupby('cluster')['mean'].mean().sort_values(ascending=False).index
            mapping = {
                mean_order[0]: 'clear',
                mean_order[1]: 'cloudy',
                mean_order[2]: 'very cloudy'
            }
            daily['weather_state'] = daily['cluster'].map(mapping)
        else:
            daily['weather_state'] = 'clear'
        
        dataset['weather_state'] = daily['weather_state'].reindex(dataset.index, method='ffill')

    # robust 통계용 설정
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
        dataset[[light_col, 'weather_state']]
        .dropna()
        .rename(columns={light_col: 'light'})
    )

    hourly_stats = (
        light_ctx
        .groupby([pd.Series(safe_hour_extract(light_ctx.index), index=light_ctx.index).rename('hour'), 'weather_state'])  # 🔴 안전
        .agg(
            median_hour=('light', 'median'),
            mad_hour=('light', robust_mad),
            q01_hour=('light', lambda s: np.quantile(s, PERCENTILE_LOW)),
            q99_hour=('light', lambda s: np.quantile(s, 0.99)),
            p25_hour=('light', lambda s: np.quantile(s, 0.25)),
            p75_hour=('light', lambda s: np.quantile(s, 0.75)),
            count_hour=('light', 'size'),
        )
        .reset_index()
    )

    full = (
        dataset[[light_col, 'weather_state']]
        .copy()
        .rename(columns={light_col: 'light'})
    )
    full['hour'] = safe_hour_extract(full.index)  # 🔴 안전

    idx_name = dataset.index.name if dataset.index.name is not None else 'index'
    full = (
        full
        .reset_index()
        .merge(hourly_stats, on=['hour', 'weather_state'], how='left')
        .set_index(idx_name)
    )

    full['light'] = ld.reindex(full.index)

    LIGHT_PPFD_MIN = 0.0
    LIGHT_PPFD_MAX = 3000.0
    mask_physical = (full['light'] < LIGHT_PPFD_MIN) | (full['light'] > LIGHT_PPFD_MAX)

    iqr = (full['p75_hour'] - full['p25_hour']).abs()
    lower_bound = full['median_hour'] - IQR_LOWER_K * iqr
    upper_bound = full['median_hour'] + IQR_UPPER_K * iqr
    mask_iqr_lower = full['light'] < lower_bound
    mask_iqr_upper = full['light'] > upper_bound
    mask_iqr = (mask_iqr_lower | mask_iqr_upper).fillna(False)

    mad = full['mad_hour'].replace(0, np.nan)
    robust_z = (full['light'] - full['median_hour']).abs() / (mad + 1e-9)
    mask_mad_extreme = robust_z > MAD_Z_UPPER

    is_day = (full['hour'] >= 9) & (full['hour'] <= 16)  # 🔴 안전
    mask_day_low = (full['light'] < full['q01_hour']) & is_day

    diff_light = full['light'].diff().fillna(0)
    mask_spike = (diff_light.abs() > 400)

    prev = full['light'].shift(1)
    drop_mask = (full['light'] <= prev * (1 - CLOUD_DROP_PERC))
    recovery_mask = pd.Series(False, index=full.index)
    for i in range(len(full)):
        if i + CLOUD_RECOVER_WINDOW < len(full):
            if i > 0 and full['light'].iat[i] <= full['light'].iat[i - 1] * (1 - CLOUD_DROP_PERC):
                after_max = full['light'].iloc[i + 1:i + 1 + CLOUD_RECOVER_WINDOW].max()
                if after_max >= full['light'].iat[i - 1] * (1 - CLOUD_DROP_PERC) * (1 + CLOUD_RECOVER_PERC):
                    recovery_mask.iat[i] = True
    mask_cloud = (drop_mask & recovery_mask).fillna(False)

    candidate = (mask_physical |
                 mask_iqr |
                 mask_mad_extreme |
                 mask_spike |
                 mask_day_low)

    cand_int = candidate.astype(int)
    groups = (cand_int != cand_int.shift(1)).cumsum()
    seg_len = cand_int.groupby(groups).transform('sum')
    min_len_samples = max(1, int(MIN_DURATION_MINUTES / SAMPLE_MINUTES))
    persistent = (cand_int == 1) & (seg_len >= min_len_samples)

    context_normal = (~mask_iqr) & (~mask_mad_extreme)
    night_mask = (full['hour'] >= 18) | (full['hour'] <= 6)  # 🔴 안전
    night_normal = (full['light'] <= 50) & night_mask
    environment_mask = context_normal | night_normal | mask_cloud

    final_faults = persistent & (~environment_mask)
    light_fault = final_faults.reindex(dataset.index, fill_value=False)

    # ============================================================
    # C. NaN 마킹
    # ============================================================

    dataset.loc[temp_fault.values, temp_col] = np.nan
    dataset.loc[hum_fault.values, humi_col] = np.nan
    dataset.loc[light_fault.values, light_col] = np.nan

    if 'weather_state' in dataset.columns:
        dataset = dataset.drop(columns=['weather_state'])

    dataset = dataset.reset_index()
    return dataset
