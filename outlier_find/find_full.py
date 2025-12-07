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


def find_outlier_df(df, temp_index, humi_index, light_index):
    """
    df에서 온도/습도/조도 이상치를 탐지하여,
    '센서 오류로 판단된 지점'만 NaN으로 마킹해 반환합니다.
    - 온도/습도: 물리 범위 + diff+zscore + 시간대별 3.5σ + 온도·습도 상관관계 기반 필터
    - 조도(PPFD): robust 통계(IQR, MAD, quantile) + spike + 낮시간 저값 + 구름 패턴 +
                  최소 지속시간 조건 + 환경 마스크를 통해 센서 오류만 남김
    """
    cols = df.columns.tolist()
    temp_col = cols[temp_index]
    humi_col = cols[humi_index]
    light_col = cols[light_index]

    dataset = df.copy()

    # 1. 인덱스 설정
    if 'date_time' in dataset.columns:
        dataset['date_time'] = pd.to_datetime(dataset['date_time'])
        dataset = dataset.set_index('date_time').sort_index()
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

    # (3) 시간대별(시각 기준) 문맥 3.5σ 밴드
    # 시각별 통계
    temp_nonan = temp.dropna()
    hum_nonan = hum.dropna()

    # 시각: index.time 사용
    hourly_temp_stats = temp_nonan.groupby(temp_nonan.index.time).agg(
        median_temp='median', std_temp='std'
    )
    hourly_hum_stats = hum_nonan.groupby(hum_nonan.index.time).agg(
        median_hum='median', std_hum='std'
    )

    # 온도 문맥
    temp_with_ctx = temp_nonan.to_frame(name='temperature')
    temp_with_ctx['time_of_day'] = temp_with_ctx.index.time
    temp_with_ctx = temp_with_ctx.merge(
        hourly_temp_stats,
        left_on='time_of_day',
        right_index=True,
        how='left'
    )
    temp_with_ctx['upper_3_5sigma'] = (
        temp_with_ctx['median_temp'] + 3.5 * temp_with_ctx['std_temp']
    )
    temp_with_ctx['lower_3_5sigma'] = (
        temp_with_ctx['median_temp'] - 3.5 * temp_with_ctx['std_temp']
    )

    anomaly_temp_ctx = (
        (temp_with_ctx['temperature'] > temp_with_ctx['upper_3_5sigma']) |
        (temp_with_ctx['temperature'] < temp_with_ctx['lower_3_5sigma'])
    ).fillna(False)

    # 습도 문맥
    hum_with_ctx = hum_nonan.to_frame(name='humidity')
    hum_with_ctx['time_of_day'] = hum_with_ctx.index.time
    hum_with_ctx = hum_with_ctx.merge(
        hourly_hum_stats,
        left_on='time_of_day',
        right_index=True,
        how='left'
    )
    hum_with_ctx['upper_3_5sigma'] = (
        hum_with_ctx['median_hum'] + 3.5 * hum_with_ctx['std_hum']
    )
    hum_with_ctx['lower_3_5sigma'] = (
        hum_with_ctx['median_hum'] - 3.5 * hum_with_ctx['std_hum']
    ).clip(lower=0)

    anomaly_hum_ctx = (
        (hum_with_ctx['humidity'] > hum_with_ctx['upper_3_5sigma']) |
        (hum_with_ctx['humidity'] < hum_with_ctx['lower_3_5sigma'])
    ).fillna(False)

    # 인덱스 재정렬 (full index 기준)
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

    # (4) 시간대별 온도–습도 상관관계 기반 센서 오류 필터
    combined = dataset[[temp_col, humi_col]].copy()
    combined.columns = ['temperature', 'humidity']
    combined['time_of_day'] = combined.index.time

    hourly_corr = (
        combined
        .dropna(subset=['temperature', 'humidity'])
        .groupby('time_of_day')[['temperature', 'humidity']]
        .corr()
        .unstack()
        .iloc[:, 1]  # temperature-humidity 상관계수
    )

    # 문맥 통합용 프레임
    merged_anom = temp_with_ctx[['temperature', 'time_of_day', 'median_temp']].copy()
    merged_anom['humidity'] = hum_with_ctx['humidity']
    merged_anom['median_hum'] = hum_with_ctx['median_hum']
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

        # Case A: 한쪽만 이상 + 상관관계 강함 → 센서오류 의심
        if (is_temp_anom != is_hum_anom) and (abs(corr_val) > STRONG_CORR_TH):
            merged_anom.at[idx, 'sensor_error_candidate'] = True

        # Case B: 둘 다 이상인데 상관 방향과 dev 방향 불일치 → 센서오류
        elif is_temp_anom and is_hum_anom:
            temp_dev = row['temperature'] - row['median_temp']
            hum_dev = row['humidity'] - row['median_hum']
            is_consistent = False

            if corr_val < -STRONG_CORR_TH:  # 음의 상관: 서로 반대여야 정상
                if (temp_dev * hum_dev) < 0:
                    is_consistent = True
            elif corr_val > STRONG_CORR_TH:  # 양의 상관: 같이 움직여야 정상
                if (temp_dev * hum_dev) > 0:
                    is_consistent = True
            else:
                # 상관 약하면 환경 변화로 간주
                is_consistent = True

            if not is_consistent:
                merged_anom.at[idx, 'sensor_error_candidate'] = True

    # 최종 센서 오류 후보 마스크 (원 인덱스로 확장)
    sensor_err_temp = all_anom_temp & merged_anom['sensor_error_candidate'].reindex(
        all_anom_temp.index, fill_value=False
    )
    sensor_err_hum = all_anom_hum & merged_anom['sensor_error_candidate'].reindex(
        all_anom_hum.index, fill_value=False
    )

    temp_fault = sensor_err_temp.fillna(False)
    hum_fault = sensor_err_hum.fillna(False)

    # ============================================================
    # B. 조도(PPFD) 이상치 탐지
    # ============================================================

    # 조도 값이 이미 PPFD 단위라고 가정
    ld = light

    # weather_state 생성
    if 'weather_state' not in dataset.columns:
        daily = ld.resample('D').agg(['max', 'mean', 'std', 'median']).dropna()
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

    # light_ctx: hour × weather_state 통계 계산
    light_ctx = (
        dataset[[light_col, 'weather_state']]
        .dropna()
        .rename(columns={light_col: 'light'})
    )

    hourly_stats = (
        light_ctx
        .groupby([light_ctx.index.hour.rename('hour'), 'weather_state'])
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
    full['hour'] = full.index.hour

    # 인덱스 이름
    idx_name = dataset.index.name if dataset.index.name is not None else 'index'
    full = (
        full
        .reset_index()
        .merge(hourly_stats, on=['hour', 'weather_state'], how='left')
        .set_index(idx_name)
    )

    # 원 조도 다시 매핑
    full['light'] = ld.reindex(full.index)

    # 물리 범위
    LIGHT_PPFD_MIN = 0.0
    LIGHT_PPFD_MAX = 3000.0
    mask_physical = (full['light'] < LIGHT_PPFD_MIN) | (full['light'] > LIGHT_PPFD_MAX)

    # IQR 기반
    iqr = (full['p75_hour'] - full['p25_hour']).abs()
    lower_bound = full['median_hour'] - IQR_LOWER_K * iqr
    upper_bound = full['median_hour'] + IQR_UPPER_K * iqr
    mask_iqr_lower = full['light'] < lower_bound
    mask_iqr_upper = full['light'] > upper_bound
    mask_iqr = (mask_iqr_lower | mask_iqr_upper).fillna(False)

    # MAD extreme
    mad = full['mad_hour'].replace(0, np.nan)
    robust_z = (full['light'] - full['median_hour']).abs() / (mad + 1e-9)
    mask_mad_extreme = robust_z > MAD_Z_UPPER

    # 낮 시간대 매우 낮은 값
    is_day = (full.index.hour >= 9) & (full.index.hour <= 16)
    mask_day_low = (full['light'] < full['q01_hour']) & is_day

    # 급격 스파이크
    diff_light = full['light'].diff().fillna(0)
    mask_spike = (diff_light.abs() > 400)

    # 구름 패턴 (급락 후 일정 시간 내 회복)
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

    # 후보 집계
    candidate = (mask_physical |
                 mask_iqr |
                 mask_mad_extreme |
                 mask_spike |
                 mask_day_low)

    # 지속성 필터(persistence)
    cand_int = candidate.astype(int)
    groups = (cand_int != cand_int.shift(1)).cumsum()
    seg_len = cand_int.groupby(groups).transform('sum')
    min_len_samples = max(1, int(MIN_DURATION_MINUTES / SAMPLE_MINUTES))
    persistent = (cand_int == 1) & (seg_len >= min_len_samples)

    # 환경 마스크
    context_normal = (~mask_iqr) & (~mask_mad_extreme)
    night_mask = (full.index.hour >= 18) | (full.index.hour <= 6)
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

    # 인덱스 복구
    dataset = dataset.reset_index()
    return dataset