import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.stats import zscore
from statsmodels.tsa.seasonal import STL
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings

# 경고 무시
warnings.filterwarnings('ignore')

# =============================================================================
# 1. 설정 (Configuration)
# =============================================================================

# CSV 파일 경로
FILE_PATH = 'mc_3m.csv'

# ❤ 열 위치 설정 (0부터 시작)
#   -> 이 부분만 파일마다 바꿔주면 됨!
dt_loc = 0   # date_time 이 있는 열 위치
t_loc  = 1   # 온도 열 위치
h_loc  = 3   # 습도 열 위치
l_loc  = 4   # 조도(light_PPFD) 열 위치
c_loc  = 5   # CO2 열 위치 (없으면 None으로 두고 아래 맵에서 빼도 됨)

# ↔ 위치 → 표준 이름 맵핑
location_map = {
    dt_loc: 'date_time',
    t_loc:  'temperature',
    h_loc:  'humidity',
    l_loc:  'light',
    c_loc:  'co2',
}


# =============================================================================
# 2. 데이터 로드 및 전처리 (Data Loading)
# =============================================================================
def load_and_preprocess(file_path, column_location_map):
    print(f"파일 로딩 : {file_path}")

    # 1. 파일 읽기
    df_raw = pd.read_csv(file_path)
    df_original_full = df_raw.copy() # 원본 전체 데이터프레임을 보존

    # Create a new DataFrame containing only the explicitly mapped columns
    # This prevents unmapped columns from `df_raw` that might have conflicting names
    # from being carried over, and ensures standard names are unique.
    data_to_build = {}
    for original_idx, standard_name in column_location_map.items():
        if original_idx < len(df_raw.columns):
            data_to_build[standard_name] = df_raw.iloc[:, original_idx]
        else:
            print(f"Warning: Column index {original_idx} (for {standard_name}) specified in location_map is out of bounds for the CSV file (max index {len(df_raw.columns)-1}). This column will be ignored.")

    df = pd.DataFrame(data_to_build)

    # Ensure 'date_time' column exists and is used as index
    if 'date_time' not in df.columns:
        raise ValueError("The 'date_time' column (as specified by dt_loc) was not found after mapping.")

    # 2. 인덱스 설정 (Time Series)
    df['date_time'] = pd.to_datetime(df['date_time'])
    df = df.set_index('date_time').sort_index()

    # 4. 중복 인덱스 제거
    if not df.index.is_unique:
        print("중복 시간 인덱스 제거 및 첫 번째 인덱스 유지")
        df = df[~df.index.duplicated(keep='first')]


#= (A2 / 60) * 4.6  J/m²
        # =========================================
    # 📌 J/m² → PPFD(µmol m⁻² s⁻¹) 변환
    #    공식: PPFD = (J/m² / 60) * 4.6
    # =========================================

    if 'light' in df.columns:
        df['light_ppfd'] = (df['light'] / 60) * 4.6   # 변환된 PPFD 값 생성
    else:
        raise KeyError("원본 파일에 'light' 열이 없습니다. (J/m² 단위)")

    # 이후 분석에서 사용할 조도 컬럼을 light_ppfd 로 지정
    l_loc = 'light_ppfd'



    # 5. 숫자형 변환 (오류 문자열은 NaN 처리)
    numeric_cols = [col for col in df.columns if col != 'date_time']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    print(f"데이터 로드 완료. 기간: {df.index.min()} ~ {df.index.max()}")
    print(f"데이터 크기: {df.shape}")
    return df, df_original_full

# 데이터 로드 실행
dataset, df_original_format = load_and_preprocess(FILE_PATH, location_map)
temp = dataset['temperature'].dropna()
hum = dataset['humidity'].dropna()

# Now dataset['light_ppfd'] should unambiguously refer to the single 'light_ppfd' column (from original l_loc index 4)
light_data = dataset['light_ppfd'].dropna()

# 문맥 정보 병합용 초기 데이터프레임
temp_with_context = temp.to_frame(name='temperature')
hum_with_context = hum.to_frame(name='humidity')
light_data_with_context = light_data.to_frame(name='light')

# Daily trend visualization
daily_temp = temp.resample('D').mean()
daily_hum = hum.resample('D').mean()
daily_light = light_data.resample('D').mean()

print(f"조도(light_PPFD) 데이터 최소값: {light_data.min()}")
print(f"조도(light_PPFD) 데이터 최대값: {light_data.max()}")

# feature별 결측치 수량 확인
dataset.isnull().sum()

# feature 중 NaN이 포함된 row 확인
dataset.loc[dataset.isnull().any(axis=1)]

# =============================================================================
# 0. 필요 라이브러리
# =============================================================================
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import zscore

# temp, hum, dataset, light_data 는 이미 정의되어 있다고 가정:
# temp = dataset['temperature']
# hum  = dataset['humidity']
# light_data = dataset['light_ppfd']  # 조도(ppfd)


# =============================================================================
# 1. 과정 시각화 헬퍼 함수
# =============================================================================
def plot_process_visualization(data_series, anomaly_mask, title,
                               lower_bound=None, upper_bound=None,
                               fill_band=True):
    """
    데이터와 함께 '판단 기준(범위)'을 시각화하여 과정을 보여주는 함수
    """
    plt.figure(figsize=(15, 6))

    # 1. 원본 데이터 (배경)
    plt.plot(data_series.index, data_series.values,
             color='gray', alpha=0.6, label='Raw Data', linewidth=1)

    # 2-1. Series 형태의 동적 범위 (예: 3.5시그마 밴드)
    if isinstance(lower_bound, (pd.Series, pd.DataFrame)) and isinstance(upper_bound, (pd.Series, pd.DataFrame)):
        lb = lower_bound.reindex(data_series.index)
        ub = upper_bound.reindex(data_series.index)
        if fill_band:
            plt.fill_between(data_series.index, lb, ub,
                             color='#2ecc71', alpha=0.2,
                             label='Normal Range (Criteria)')
        plt.plot(data_series.index, lb, color='#27ae60',
                 linestyle='--', linewidth=0.8, alpha=0.5)
        plt.plot(data_series.index, ub, color='#27ae60',
                 linestyle='--', linewidth=0.8, alpha=0.5)

    # 2-2. 고정 값 임계치 (예: 물리적 범위)
    elif isinstance(lower_bound, (int, float)) and isinstance(upper_bound, (int, float)):
        plt.axhline(lower_bound, color='orange', linestyle='--',
                    label=f'Min Limit ({lower_bound})')
        plt.axhline(upper_bound, color='orange', linestyle='--',
                    label=f'Max Limit ({upper_bound})')

    # 3. 탐지된 이상치
    anomalies = data_series[anomaly_mask]
    if not anomalies.empty:
        plt.scatter(anomalies.index, anomalies.values,
                    color='red', s=30, zorder=5, label='Detected Anomaly')

    plt.title(title, fontsize=14, fontweight='bold')
    plt.legend(loc='upper right')
    plt.grid(True, linestyle='--', alpha=0.3)
    plt.tight_layout()
    plt.show()


# =============================================================================
# 2. 온도/습도 이상치 탐지 (물리 + 급변 + 문맥 + 상관관계)
# =============================================================================
print("\n[Step 1] 온도/습도 물리적 및 급변 탐지...")

# (1) 물리적 범위 필터
TEMP_MIN, TEMP_MAX = -10, 50
HUM_MIN,  HUM_MAX  = 0, 100
LIGHT_PPFD_MIN, LIGHT_PPFD_MAX = 0, 4000  # PPFD 물리적 범위

temp_physical  = (temp < TEMP_MIN) | (temp > TEMP_MAX)
hum_physical   = (hum  < HUM_MIN)  | (hum  > HUM_MAX)
light_physical = (light_data < LIGHT_PPFD_MIN) | (light_data > LIGHT_PPFD_MAX)

# (2) 차분 + z-score 기반 급변 탐지
diff_temp = temp.diff()
diff_hum  = hum.diff()
z_temp = zscore(diff_temp, nan_policy='omit')
z_hum  = zscore(diff_hum,  nan_policy='omit')
Z_THRESH = 4

cond_temp_diff = pd.Series(np.abs(z_temp) > Z_THRESH,
                           index=temp.index).fillna(False)
cond_hum_diff  = pd.Series(np.abs(z_hum)  > Z_THRESH,
                           index=hum.index).fillna(False)

# ▶ 물리적 범위 시각화
plot_process_visualization(temp, temp_physical,
                           "1-1. Temperature Physical Range Check",
                           lower_bound=TEMP_MIN, upper_bound=TEMP_MAX)
plot_process_visualization(hum, hum_physical,
                           "1-1. Humidity Physical Range Check",
                           lower_bound=HUM_MIN, upper_bound=HUM_MAX)

print("\n[Step 2] 온도/습도 시간대별 문맥적(3.5σ) 탐지...")

# 시간대별 통계 및 3.5σ 계산
hourly_temp_stats = temp.groupby(temp.index.time).agg(
    median_temp='median', std_temp='std'
)
hourly_hum_stats = hum.groupby(hum.index.time).agg(
    median_hum='median', std_hum='std'
)

# 온도 문맥 병합
temp_with_context = temp.to_frame(name='temperature')
temp_with_context['time_of_day'] = temp_with_context.index.time
temp_with_context = temp_with_context.merge(
    hourly_temp_stats, left_on='time_of_day', right_index=True, how='left'
)
temp_with_context['upper_3_5sigma'] = (
    temp_with_context['median_temp'] + 3.5 * temp_with_context['std_temp']
)
temp_with_context['lower_3_5sigma'] = (
    temp_with_context['median_temp'] - 3.5 * temp_with_context['std_temp']
)

# 습도 문맥 병합
hum_with_context = hum.to_frame(name='humidity')
hum_with_context['time_of_day'] = hum_with_context.index.time
hum_with_context = hum_with_context.merge(
    hourly_hum_stats, left_on='time_of_day', right_index=True, how='left'
)
hum_with_context['upper_3_5sigma'] = (
    hum_with_context['median_hum'] + 3.5 * hum_with_context['std_hum']
)
hum_with_context['lower_3_5sigma'] = (
    hum_with_context['median_hum'] - 3.5 * hum_with_context['std_hum']
).clip(lower=0)

# 3.5σ 이상치 판별
anomaly_temp_3_5sigma_contextual = (
    (temp_with_context['temperature'] > temp_with_context['upper_3_5sigma']) |
    (temp_with_context['temperature'] < temp_with_context['lower_3_5sigma'])
).fillna(False)

anomaly_hum_3_5sigma_contextual = (
    (hum_with_context['humidity'] > hum_with_context['upper_3_5sigma']) |
    (hum_with_context['humidity'] < hum_with_context['lower_3_5sigma'])
).fillna(False)

print("\n  (1) 물리적 범위 이상치:\n")
print(f"  - 온도 물리적 범위 이상치: {temp_physical.sum()}개")
print(f"  - 습도 물리적 범위 이상치: {hum_physical.sum()}개")
print(f"  - 조도(PPFD) 물리적 범위 이상치: {light_physical.sum()}개")

print("\n  (2) 시간대별 문맥적 (3.5σ) 이상치:\n")
print(f"  - 온도 문맥적 3.5σ 이상치: {anomaly_temp_3_5sigma_contextual.sum()}개")
print(f"  - 습도 문맥적 3.5σ 이상치: {anomaly_hum_3_5sigma_contextual.sum()}개")

# ▶ 문맥적 밴드 시각화
plot_process_visualization(
    temp, anomaly_temp_3_5sigma_contextual,
    "1-2. Temperature Contextual Check (3.5σ Band)",
    lower_bound=temp_with_context['lower_3_5sigma'],
    upper_bound=temp_with_context['upper_3_5sigma']
)

plot_process_visualization(
    hum, anomaly_hum_3_5sigma_contextual,
    "1-3. Humidity Contextual Check (3.5σ Band)",
    lower_bound=hum_with_context['lower_3_5sigma'],
    upper_bound=hum_with_context['upper_3_5sigma']
)

print("\n[Step 3] 상관관계 기반 필터링 (환경 vs 센서오류)...")

# 모든 이상치 통합
all_anomalies_temp = (temp_physical |
                      cond_temp_diff |
                      anomaly_temp_3_5sigma_contextual)

all_anomalies_hum = (hum_physical |
                     cond_hum_diff |
                     anomaly_hum_3_5sigma_contextual)

# 시간대별 상관관계
combined_sensor_data = dataset[['temperature', 'humidity']].copy()
combined_sensor_data['time_of_day'] = combined_sensor_data.index.time
hourly_corr = (
    combined_sensor_data
    .groupby('time_of_day')[['temperature', 'humidity']]
    .corr()
    .unstack()
    .iloc[:, 1]        # temperature-humidity 상관계수
)

# 상관관계 + 중앙값 기준으로 센서오류 후보 판단
merged_anomalies = temp_with_context[['temperature', 'time_of_day', 'median_temp']].copy()
merged_anomalies['humidity']   = hum_with_context['humidity']
merged_anomalies['median_hum'] = hum_with_context['median_hum']
merged_anomalies['anomaly_temp_total'] = all_anomalies_temp
merged_anomalies['anomaly_hum_total']  = all_anomalies_hum
merged_anomalies = merged_anomalies.merge(
    hourly_corr.rename('hourly_correlation'),
    left_on='time_of_day', right_index=True, how='left'
)

STRONG_CORRELATION_THRESHOLD = 0.5
merged_anomalies['sensor_error_candidate'] = False

for idx, row in merged_anomalies.iterrows():
    is_temp_anom = row['anomaly_temp_total']
    is_hum_anom  = row['anomaly_hum_total']
    corr_val     = row['hourly_correlation']

    if pd.isna(corr_val):
        continue

    # Case A: 한쪽만 이상 + 상관관계 강함 → 센서오류 의심
    if (is_temp_anom != is_hum_anom) and (abs(corr_val) > STRONG_CORRELATION_THRESHOLD):
        merged_anomalies.loc[idx, 'sensor_error_candidate'] = True

    # Case B: 둘 다 이상인데 상관관계 방향과 dev 방향이 안 맞으면 → 센서오류
    elif is_temp_anom and is_hum_anom:
        temp_dev = row['temperature'] - row['median_temp']
        hum_dev  = row['humidity']   - row['median_hum']
        is_consistent = False

        if corr_val < -STRONG_CORRELATION_THRESHOLD:     # 음의 상관: 서로 반대여야 정상
            if (temp_dev * hum_dev) < 0:
                is_consistent = True
        elif corr_val > STRONG_CORRELATION_THRESHOLD:    # 양의 상관: 같이 움직여야 정상
            if (temp_dev * hum_dev) > 0:
                is_consistent = True
        else:
            is_consistent = True  # 상관 약하면 환경 변화로 간주

        if not is_consistent:
            merged_anomalies.loc[idx, 'sensor_error_candidate'] = True

# 최종 후보 마스크
potential_sensor_error_temp = (all_anomalies_temp &
                               merged_anomalies['sensor_error_candidate'])
potential_sensor_error_hum = (all_anomalies_hum &
                              merged_anomalies['sensor_error_candidate'])

print(f"\n[Step 3 결과] 상관관계 기반 센서 오류 후보")
print(f"  - 온도 센서 최종 오류 후보: {potential_sensor_error_temp.sum()}개")
print(f"  - 습도 센서 최종 오류 후보: {potential_sensor_error_hum.sum()}개")


# =============================================================================
# 3. 최종 마스크 정리 + 3-패널 시각화 (Original / Flagged / Cleaned)
# =============================================================================

# ----- (1) 마스크 정의 -----
# 초기(all) = 통합 이상치
mask_temp_all   = all_anomalies_temp.copy()
mask_hum_all    = all_anomalies_hum.copy()

# 최종(sensor error) = 상관관계 필터 통과
mask_temp_final = potential_sensor_error_temp.copy()
mask_hum_final  = potential_sensor_error_hum.copy()

# 환경/정상 쪽으로 걸러진 것들 (초기 - 최종)
mask_temp_env   = mask_temp_all & ~mask_temp_final
mask_hum_env    = mask_hum_all  & ~mask_hum_final

# ----- (2) 인덱스 정렬 (길이 불일치 방지용) -----
mask_temp_all   = mask_temp_all.reindex(temp.index, fill_value=False)
mask_temp_env   = mask_temp_env.reindex(temp.index, fill_value=False)
mask_temp_final = mask_temp_final.reindex(temp.index, fill_value=False)

mask_hum_all    = mask_hum_all.reindex(hum.index, fill_value=False)
mask_hum_env    = mask_hum_env.reindex(hum.index, fill_value=False)
mask_hum_final  = mask_hum_final.reindex(hum.index, fill_value=False)

# ----- (3) Cleaned series (최종 오류 → NaN) -----
temp_clean = temp.copy()
hum_clean  = hum.copy()

temp_clean.loc[mask_temp_final] = np.nan
hum_clean.loc[mask_hum_final]   = np.nan

# 문맥 밴드 재정렬
temp_lb = temp_with_context['lower_3_5sigma'].reindex(temp.index)
temp_ub = temp_with_context['upper_3_5sigma'].reindex(temp.index)
hum_lb  = hum_with_context['lower_3_5sigma'].reindex(hum.index)
hum_ub  = hum_with_context['upper_3_5sigma'].reindex(hum.index)

# ----- (4) 3-패널 시각화 -----
fig, axes = plt.subplots(2, 3, figsize=(20, 10), sharex='col')

def draw_common(ax, series, lb=None, ub=None,
                phys_min=None, phys_max=None, title_extra=""):
    ax.plot(series.index, series.values,
            color='gray', alpha=0.6, linewidth=1)
    # 문맥 밴드
    if isinstance(lb, pd.Series) and isinstance(ub, pd.Series):
        ax.fill_between(series.index, lb, ub,
                        color='#d4f7dc', alpha=0.25)
        ax.plot(series.index, lb, color='#27ae60',
                linestyle='--', linewidth=0.7, alpha=0.6)
        ax.plot(series.index, ub, color='#27ae60',
                linestyle='--', linewidth=0.7, alpha=0.6)
    # 물리적 범위
    if phys_min is not None:
        ax.axhline(phys_min, color='orange', linestyle='--', linewidth=1)
    if phys_max is not None:
        ax.axhline(phys_max, color='orange', linestyle='--', linewidth=1)
    if title_extra:
        ax.set_title(title_extra, fontsize=11, fontweight='bold')

# ---- Row 1: Temperature ----
# (1) Original
ax = axes[0, 0]
draw_common(ax, temp, lb=temp_lb, ub=temp_ub,
            phys_min=TEMP_MIN, phys_max=TEMP_MAX,
            title_extra="Temperature — (1) Original")
ax.set_ylabel('Temperature (°C)', fontsize=12)
ax.grid(True, linestyle='--', alpha=0.3)

# (2) Flagged
ax = axes[0, 1]
draw_common(ax, temp, lb=temp_lb, ub=temp_ub,
            phys_min=TEMP_MIN, phys_max=TEMP_MAX,
            title_extra="Temperature — (2) Flagged Anomalies")
ax.scatter(temp.index[mask_temp_all], temp[mask_temp_all],
           s=18, color='gray', alpha=0.6,
           label='Initial Anomaly (all)', zorder=4)
ax.scatter(temp.index[mask_temp_env], temp[mask_temp_env],
           s=60, facecolors='none', edgecolors='orange',
           linewidths=1.2, label='Environment (filtered out)', zorder=5)
ax.scatter(temp.index[mask_temp_final], temp[mask_temp_final],
           marker='o', s=50, color='red',
           label='Final Sensor Error', zorder=7)
ax.legend(loc='upper left')
ax.grid(True, linestyle='--', alpha=0.3)

# (3) Cleaned
ax = axes[0, 2]
draw_common(ax, temp_clean, lb=temp_lb, ub=temp_ub,
            phys_min=TEMP_MIN, phys_max=TEMP_MAX,
            title_extra="Temperature — (3) Cleaned (errors→NaN)")
ax.scatter(temp.index[mask_temp_final], temp[mask_temp_final],
           marker='x', s=40, color='red',
           label='Removed (was error)', zorder=6)
ax.legend(loc='upper left')
ax.grid(True, linestyle='--', alpha=0.3)

# ---- Row 2: Humidity ----
# (1) Original
ax = axes[1, 0]
draw_common(ax, hum, lb=hum_lb, ub=hum_ub,
            phys_min=HUM_MIN, phys_max=HUM_MAX,
            title_extra="Humidity — (1) Original")
ax.set_ylabel('Humidity (%)', fontsize=12)
ax.grid(True, linestyle='--', alpha=0.3)

# (2) Flagged
ax = axes[1, 1]
draw_common(ax, hum, lb=hum_lb, ub=hum_ub,
            phys_min=HUM_MIN, phys_max=HUM_MAX,
            title_extra="Humidity — (2) Flagged Anomalies")
ax.scatter(hum.index[mask_hum_all], hum[mask_hum_all],
           s=18, color='gray', alpha=0.6,
           label='Initial Anomaly (all)', zorder=4)
ax.scatter(hum.index[mask_hum_env], hum[mask_hum_env],
           s=60, facecolors='none', edgecolors='orange',
           linewidths=1.2, label='Environment (filtered out)', zorder=5)
ax.scatter(hum.index[mask_hum_final], hum[mask_hum_final],
           marker='o', s=50, color='red',
           label='Final Sensor Error', zorder=7)
ax.legend(loc='upper left')
ax.grid(True, linestyle='--', alpha=0.3)

# (3) Cleaned
ax = axes[1, 2]
draw_common(ax, hum_clean, lb=hum_lb, ub=hum_ub,
            phys_min=HUM_MIN, phys_max=HUM_MAX,
            title_extra="Humidity — (3) Cleaned (errors→NaN)")
ax.scatter(hum.index[mask_hum_final], hum[mask_hum_final],
           marker='x', s=40, color='red',
           label='Removed (was error)', zorder=6)
ax.legend(loc='upper left')
ax.grid(True, linestyle='--', alpha=0.3)

plt.xlabel('Time')
plt.tight_layout()

# 요약 텍스트
temp_initial_count = int(mask_temp_all.sum())
temp_env_count     = int(mask_temp_env.sum())
temp_final_count   = int(mask_temp_final.sum())
hum_initial_count  = int(mask_hum_all.sum())
hum_env_count      = int(mask_hum_env.sum())
hum_final_count    = int(mask_hum_final.sum())

summary_text = (
    f"Temperature: initial {temp_initial_count}, env-filtered {temp_env_count}, final-error {temp_final_count}\n"
    f"Humidity   : initial {hum_initial_count}, env-filtered {hum_env_count}, final-error {hum_final_count}"
)
plt.gcf().text(
    0.01, 0.01, summary_text,
    fontsize=10,
    bbox=dict(facecolor='white', alpha=0.7, edgecolor='none')
)

plt.show()

# ============================================
# 이상치 단계별 개수 + 값 출력 (인덱스 정렬 포함)
# ============================================

# 0) 우선 모든 마스크를 dataset 인덱스에 정렬해서 안전하게 맞춰줌
temp_physical_ds   = temp_physical.reindex(dataset.index, fill_value=False)
hum_physical_ds    = hum_physical.reindex(dataset.index, fill_value=False)

cond_temp_diff_ds  = cond_temp_diff.reindex(dataset.index, fill_value=False)
cond_hum_diff_ds   = cond_hum_diff.reindex(dataset.index, fill_value=False)

anomaly_temp_ctx_ds = anomaly_temp_3_5sigma_contextual.reindex(dataset.index, fill_value=False)
anomaly_hum_ctx_ds  = anomaly_hum_3_5sigma_contextual.reindex(dataset.index, fill_value=False)

potential_temp_ds  = potential_sensor_error_temp.reindex(dataset.index, fill_value=False)
potential_hum_ds   = potential_sensor_error_hum.reindex(dataset.index, fill_value=False)

# 공통 출력 함수
def print_mask_step(
    title,
    temp_mask,
    hum_mask,
    temp_col='temperature',
    hum_col='humidity',
    show_limit=20
):
    """단계 제목 + 온도/습도 개수 + 값 일부 출력"""
    temp_mask = temp_mask.fillna(False)
    hum_mask  = hum_mask.fillna(False)

    temp_cnt = int(temp_mask.sum())
    hum_cnt  = int(hum_mask.sum())

    print(f"\n[{title}]")
    print(f"- 온도 이상치: {temp_cnt}개")
    print(f"- 습도 이상치: {hum_cnt}개")

    # 온도 값 출력
    if temp_cnt > 0:
        print("  ▶ 온도 이상치 값 (최대 {0}개까지 표시):".format(show_limit))
        temp_idx = temp_mask[temp_mask].index[:show_limit]
        print(dataset.loc[temp_idx, [temp_col]].to_string())
    else:
        print("  ▶ 온도 이상치 값: (해당 없음)")

    # 습도 값 출력
    if hum_cnt > 0:
        print("  ▶ 습도 이상치 값 (최대 {0}개까지 표시):".format(show_limit))
        hum_idx = hum_mask[hum_mask].index[:show_limit]
        print(dataset.loc[hum_idx, [hum_col]].to_string())
    else:
        print("  ▶ 습도 이상치 값: (해당 없음)")


# -------------------------
# [Step 1] 물리적 범위 이상치
# -------------------------
print_mask_step(
    "Step 1) 물리적 범위 이상치",
    temp_physical_ds,
    hum_physical_ds,
)

# -------------------------
# [Step 1-2] 차분 + Z-score 급변
# -------------------------
print_mask_step(
    "Step 1-2) 차분(Diff) + Z-score 기반 급변 이상치",
    cond_temp_diff_ds,
    cond_hum_diff_ds,
)

# -------------------------
# [Step 2] 시간대별 문맥적 3.5σ 이상치
# -------------------------
print_mask_step(
    "Step 2) 시간대별 문맥적 3.5σ 이상치",
    anomaly_temp_ctx_ds,
    anomaly_hum_ctx_ds,
)

# -------------------------
# [Step 3] 상관관계 기반 센서 오류 후보
# -------------------------
print_mask_step(
    "Step 3) 상관관계 기반 센서 오류 후보",
    potential_temp_ds,
    potential_hum_ds,
)

"""✔ 온도 오류 4개

이 시점에서 습도와의 상관 패턴이 무너졌던 값이라서 센서 오작동 가능성이 있다고 판단된 것.

✔ 습도 오류 18개

밤 시간대 대규모 흔들림 + 온도와 패턴 불일치가 겹쳐서 걸린 것
"""


# =========================
# PPFD 이상치 탐지 + 단계별 시각화
# =========================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import os

# ---------- 설정 ----------
SAMPLE_MINUTES = 1
MIN_DURATION_MINUTES = 5
IQR_LOWER_K = 3.5
IQR_UPPER_K = 6.0
MAD_Z_UPPER = 20.0
PERCENTILE_LOW = 0.01
CLOUD_DROP_PERC = 0.4
CLOUD_RECOVER_PERC = 0.3
CLOUD_RECOVER_WINDOW = 10

# ---------- 데이터 확인 ----------
if 'dataset' not in globals():
    raise RuntimeError("dataset 필요 (light_ppfd 컬럼 포함).")
if 'light_ppfd' not in dataset.columns:
    raise RuntimeError("dataset에 'light_ppfd' 컬럼이 필요합니다.")

ld = dataset['light_ppfd']

# ---------- 0) weather_state 생성 ----------
if 'weather_state' not in dataset.columns:
    print("weather_state가 없어 일별 KMeans로 생성합니다 (n_clusters=3).")
    daily = ld.resample('D').agg(['max','mean','std','median']).dropna()
    if len(daily) >= 3:
        scaler = StandardScaler()
        df_s = scaler.fit_transform(daily)
        kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        daily['cluster'] = kmeans.fit_predict(df_s)
        mean_order = daily.groupby('cluster')['mean'].mean().sort_values(ascending=False).index
        mapping = { mean_order[0]:'clear', mean_order[1]:'cloudy', mean_order[2]:'very cloudy' }
        daily['weather_state'] = daily['cluster'].map(mapping)
    else:
        daily['weather_state'] = 'clear'
    dataset['weather_state'] = daily['weather_state'].reindex(dataset.index, method='ffill')
#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# ---------- 1) robust 통계 ----------
# ---------- 1) robust 통계 (안전 버전) ----------
def robust_mad(x):
    return np.median(np.abs(x - np.median(x)))

# hour × weather_state 별 통계 계산
light_ctx = (
    dataset[['light_ppfd', 'weather_state']]
    .dropna()
    .rename(columns={'light_ppfd': 'light'})
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

# ---------- full dataframe merge (안전 버전) ----------
full = (
    dataset[['light_ppfd', 'weather_state']]
    .copy()
    .rename(columns={'light_ppfd': 'light'})
)

full['hour'] = full.index.hour

# 인덱스 이름 확인 (없으면 'index'로 reset_index 에서 만들어짐)
idx_name = dataset.index.name if dataset.index.name is not None else 'index'

full = (
    full
    .reset_index()                # idx_name 컬럼 생김
    .merge(
        hourly_stats,
        on=['hour', 'weather_state'],
        how='left'
    )
    .set_index(idx_name)          # 다시 시간 인덱스로 복원
)

# light 컬럼을 확실히 PPFD로 유지
full['light'] = dataset['light_ppfd'].reindex(full.index)

full = full.rename(columns={'median':'median_hour','mad':'mad_hour','q01':'q01_hour','q99':'q99_hour','p25':'p25_hour','p75':'p75_hour','count':'count_hour'})

# ---------- 2) 단계별 마스크 ----------
# Physical
LIGHT_PPFD_MIN = 0.0
LIGHT_PPFD_MAX = 3000.0
mask_physical = (full['light'] < LIGHT_PPFD_MIN) | (full['light'] > LIGHT_PPFD_MAX)

# IQR
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

# Daytime very low
is_day = (full.index.hour >= 9) & (full.index.hour <= 16)
mask_day_low = (full['light'] < full['q01_hour']) & is_day

# Sudden spike
diff = full['light'].diff().fillna(0)
mask_spike = (diff.abs() > 400)

# Cloud pattern
prev = full['light'].shift(1)
drop_mask = (full['light'] <= prev * (1 - CLOUD_DROP_PERC))
recovery_mask = pd.Series(False, index=full.index)
for i in range(len(full)):
    if i + CLOUD_RECOVER_WINDOW < len(full):
        if i>0 and full['light'].iat[i] <= full['light'].iat[i-1]*(1-CLOUD_DROP_PERC):
            after_max = full['light'].iloc[i+1:i+1+CLOUD_RECOVER_WINDOW].max()
            if after_max >= full['light'].iat[i-1]*(1-CLOUD_DROP_PERC)*(1+CLOUD_RECOVER_PERC):
                recovery_mask.iat[i] = True
mask_cloud = (drop_mask & recovery_mask).fillna(False)


# ---------- 5) 후보 집계 & persistence ----------
candidate = mask_physical | mask_iqr | mask_mad_extreme | mask_spike | mask_day_low
cand_int = candidate.astype(int)
groups = (cand_int != cand_int.shift(1)).cumsum()
seg_len = cand_int.groupby(groups).transform('sum')
min_len_samples = max(1,int(MIN_DURATION_MINUTES/SAMPLE_MINUTES))
persistent = (cand_int==1) & (seg_len >= min_len_samples)

plt.figure(figsize=(15,2))
plt.plot(persistent.astype(int), color='red', lw=1)
plt.title(f"Persistent candidate mask (>= {MIN_DURATION_MINUTES} min)")
plt.show()

# ---------- 6) environment mask ----------
context_normal = (~mask_iqr) & (~mask_mad_extreme)
night_mask = (full.index.hour >= 18) | (full.index.hour <= 6)
night_normal = (full['light'] <= 50) & night_mask
environment_mask = context_normal | night_normal | mask_cloud

final_faults = persistent & (~environment_mask)
print(f"\n>> Final faults count: {int(final_faults.sum())}")

# 최종 오류 마스크를 사용하여 원본 데이터의 값을 NaN으로 대체
dataset['light_ppfd_cleaned'] = dataset['light_ppfd'].copy()
dataset.loc[final_faults, 'light_ppfd_cleaned'] = np.nan

# 만약 dataset['light_ppfd'] 자체를 수정하려면:
# dataset.loc[final_faults, 'light_ppfd'] = np.nan

# ---------- 7) reason flags ----------
final_idx = final_faults[final_faults].index
reasons = []
for ts in final_idx:
    flags = []
    if mask_physical.loc[ts]: flags.append('physical')
    if mask_iqr_upper.loc[ts] or mask_iqr_lower.loc[ts]: flags.append('iqr_out')
    if mask_mad_extreme.loc[ts]: flags.append('mad_extreme')
    if mask_spike.loc[ts]: flags.append('spike')
    if mask_day_low.loc[ts]: flags.append('day_low')
    if mask_cloud.loc[ts]: flags.append('cloud_pattern')
    env_tags = []
    if context_normal.loc[ts]: env_tags.append('context_normal')
    if night_normal.loc[ts]: env_tags.append('night_normal')
    reasons.append({
        'timestamp': ts,
        'ppfd': full.loc[ts,'light'],
        'hour': ts.hour,
        'weather_state': full.loc[ts,'weather_state'],
        'flags': ",".join(flags) if flags else 'none',
        'env_tags': ",".join(env_tags) if env_tags else 'none'
    })
reason_flags = pd.DataFrame(reasons).set_index('timestamp')
print("\n--- final faults examples (up to 20) ---")
print(reason_flags.to_string()) # Changed .head(20) to print all

"""모두 clear(맑음) 상태인데

13시대(정오 근처)에

PPFD가 120~170로 매우 낮아짐

weather_state가 clear라면 원래 500~1500 이상이어야 정상

day_low 조건과 iqr_out 패턴과 동시에 걸림

즉,
☀️ 해가 강하게 떠 있어야 하는데 값이 너무 낮아지는 패턴
→ 실제 센서 shadowing(가림), 패널 오염, 설치 방향 문제, 순간 신호 감소 등에서 나타나는 대표
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd # pd는 DataFrame을 사용하는 환경을 가정합니다.

# --- 변수 정의 (이전 로직에서 이미 계산되었다고 가정) ---
# 예시 값 (실제 실행 환경에 맞게 변수명을 확인하세요)
# ld = dataset['light_ppfd']
# final_faults = final_sensor_fault_light
# candidate = potential_sensor_error_light (또는 모든 초기 마스크의 union)
# environment_mask = environment_mask (night, cloud, contextual normal)

# --- prepare cleaned series (final sensor faults -> NaN) ---
light_clean = ld.copy()
light_clean.loc[final_faults] = np.nan

# ✅ 여기 수정: IQR 하한/상한을 밴드로 사용
light_lb = lower_bound.reindex(ld.index)
light_ub = upper_bound.reindex(ld.index)

# Environment mask에서 최종 오류로 걸러지지 않은 나머지 환경 정상 마스크를 추출합니다.
# environment_mask & ~final_faults 가 더 정확하지만, 여기서는 environment_mask에 포함된 지점 중,
# 최종 오류가 아닌 지점을 시각화하여 필터링된 지점을 확인하는 목적으로 mask_light_env를 재정의합니다.
# T/H 코드의 mask_temp_env는 환경 필터링 '당한' 지점이므로, 여기서는 그 목적에 맞게 재정의합니다.
# mask_light_env = environment_mask & candidate
mask_light_env = environment_mask.copy() # T/H 코드와 동일하게 단순 Environment mask를 사용




# --------------------
# Row 1: Light (PPFD)
# --------------------
# (1) Original
ax = axes[0]
draw_common(ax, ld, lb=light_lb, ub=light_ub, phys_min=LIGHT_PPFD_MIN, phys_max=LIGHT_PPFD_MAX,
             title_extra="PPFD Light — (1) Original")
ax.set_xlabel('Time')

# (2) Flagged (Initial, Env-filtered, Final Errors)
ax = axes[1]
draw_common(ax, ld, lb=light_lb, ub=light_ub, phys_min=LIGHT_PPFD_MIN, phys_max=LIGHT_PPFD_MAX,
             title_extra="PPFD Light — (2) Flagged Anomalies")
# Initial Candidate Anomalies (전체 오류 후보)
ax.scatter(ld.index[candidate], ld[candidate], s=18, color='gray', alpha=0.6, label='Initial Anomaly (all)', zorder=4)
# Environment Filtered Points (환경 정상으로 분류되어 필터링된 지점)
# 주의: 이 마스크는 final_faults에 포함되지 않은 env_mask 지점을 의미합니다.
ax.scatter(ld.index[mask_light_env], ld[mask_light_env], s=60, facecolors='none', edgecolors='orange', linewidths=1.2, label='Environment (filtered out)', zorder=5)
# Final Sensor Errors (최종 오류)
ax.scatter(ld.index[final_faults], ld[final_faults], marker='o', s=50, color='red', label='Final Sensor Error', zorder=7)
ax.legend(loc='upper left')
ax.set_xlabel('Time')


# (3) Cleaned (final errors -> NaN)
ax = axes[2]
draw_common(ax, light_clean, lb=light_lb, ub=light_ub, phys_min=LIGHT_PPFD_MIN, phys_max=LIGHT_PPFD_MAX,
             title_extra="PPFD Light — (3) Cleaned (errors→NaN)")
# Removed points (제거된 오류 지점 표시)
ax.scatter(ld.index[final_faults], ld[final_faults], marker='x', s=40, color='red', label='Removed (was error)', zorder=6)
ax.legend(loc='upper left')
ax.set_xlabel('Time')


# x-axis formatting and summary
plt.tight_layout()

# Summary text (counts)
light_initial_count = int(candidate.sum())
# 초기 후보 중 최종 오류가 아닌 것 (환경 필터링으로 제거되거나 지속성 미만으로 제거된 것)
light_filtered_count = light_initial_count - int(final_faults.sum())
light_final_count = int(final_faults.sum())

summary_text = (
    f"PPFD Light: initial {light_initial_count}, filtered/env-filtered {light_filtered_count}, final-error {light_final_count}"
)
plt.gcf().text(0.01, 0.01, summary_text, fontsize=10, bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))

plt.savefig('ppfd_anomaly_visualization.png')


# =============================================================================
# 4. 결과 저장
# =============================================================================
print("\n[Final] 결과 저장...")

base_name = os.path.splitext(os.path.basename(FILE_PATH))[0]
dir_name = os.path.dirname(FILE_PATH)
outcome_dir = os.path.join(dir_name, f"{base_name}_outcome")
os.makedirs(outcome_dir, exist_ok=True)

# 원본 데이터 저장 (df_original_format 사용)
original_output_path = os.path.join(outcome_dir, f"{base_name}_original.csv")
df_original_format.to_csv(original_output_path, index=False, encoding='utf-8-sig') # 인덱스를 컬럼으로 저장하지 않음
print(f"✅ 원본 데이터 파일: {original_output_path}")

# 정제된 결과 데이터 저장 (원본 포맷 유지)
cleaned_output_path = os.path.join(outcome_dir, f"{base_name}_delete_error.csv")
cleaned_output_df = df_original_format.copy() # 원본 df_raw의 포맷을 유지

# 원본 컬럼명 매핑을 위한 역방향 맵 생성
reverse_location_map = {v: k for k, v in location_map.items()}

# cleaned_output_df의 'date_time' 컬럼을 datetime 타입으로 변환하여 비교 준비
# 단, 'date_time' 컬럼이 original_df_format에 dt_loc 인덱스로 있을 때만 처리
original_dt_col_name = None
if dt_loc < len(df_original_format.columns):
    original_dt_col_name = df_original_format.columns[dt_loc]
    cleaned_output_df[original_dt_col_name] = pd.to_datetime(cleaned_output_df[original_dt_col_name])
else:
    print("Warning: Original 'date_time' column name could not be determined for cleaned output.")

if original_dt_col_name:
    # 온도 이상치 처리
    if 'temperature' in reverse_location_map:
        original_temp_col_name = df_original_format.columns[reverse_location_map['temperature']]
        temp_error_dates = potential_sensor_error_temp.index[potential_sensor_error_temp]
        cleaned_output_df.loc[cleaned_output_df[original_dt_col_name].isin(temp_error_dates), original_temp_col_name] = np.nan

    # 습도 이상치 처리
    if 'humidity' in reverse_location_map:
        original_hum_col_name = df_original_format.columns[reverse_location_map['humidity']]
        hum_error_dates = potential_sensor_error_hum.index[potential_sensor_error_hum]
        cleaned_output_df.loc[cleaned_output_df[original_dt_col_name].isin(hum_error_dates), original_hum_col_name] = np.nan

        # 조도 이상치 처리
    if 'light' in reverse_location_map:
        original_light_col_name = df_original_format.columns[reverse_location_map['light']]
        light_error_dates = final_faults.index[final_faults]   # ← 여기!
        cleaned_output_df.loc[
            cleaned_output_df[original_dt_col_name].isin(light_error_dates),
            original_light_col_name
        ] = np.nan
# cleaned_output_df.to_csv(cleaned_output_path, index=True, encoding='utf-8-sig') # 인덱스 (date_time)도 저장
cleaned_output_df.to_csv(cleaned_output_path, index=False, encoding='utf-8-sig') # 인덱스를 컬럼으로 저장하지 않음

print(f"✅ 처리가 완료되었습니다. 결과 파일: {cleaned_output_path}")


# 실시간(마지막) 체크
last_ts = temp.index[-1]
print(f"\n[실시간 감지 리포트] {last_ts}")
print(f" - 온도: {'❌ 오류' if potential_sensor_error_temp.get(last_ts, False) else '✅ 정상'}")
print(f" - 습도: {'❌ 오류' if potential_sensor_error_hum.get(last_ts, False) else '✅ 정상'}")
print(f" - 조도: {'❌ 오류' if final_faults.get(last_ts, False) else '✅ 정상'}")