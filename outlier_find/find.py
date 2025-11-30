# outlier_find/find.py
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import zscore

# =========================================
# 0. CSV 파일 경로 + 컬럼 위치 설정
# =========================================
file_path = '/content/drive/MyDrive/Colab Notebooks/2025sfdesign/PF_0000574_01(2024.09.01-2025.07.01)_clean.csv'  # CSV 경로

# 🔢 열 위치 설정 (0부터 시작)
#   -> 이 부분만 파일마다 바꿔주면 됨!
dt_loc = 0   # date_time 이 있는 열 위치
t_loc  = 7   # 온도 열 위치
h_loc  = 4   # 습도 열 위치
l_loc  = 6   # 조도(light) 열 위치
c_loc  = 1   # CO2 열 위치 (없으면 None으로 두고 아래 맵에서 빼도 됨)

# 🔁 위치 → 표준 이름 맵핑
location_map = {
    dt_loc: 'date_time',
    t_loc:  'temperature',
    h_loc:  'humidity',
    l_loc:  'light',
    c_loc:  'co2',
}

# None 들어간 거 있으면 제거 (c_loc 등을 안 쓸 때 대비)
location_map = {k: v for k, v in location_map.items() if k is not None}

# 위치를 기준으로 정렬해서 usecols와 이름 리스트 만들기
sorted_items = sorted(location_map.items(), key=lambda x: x[0])
use_cols = [idx for idx, _ in sorted_items]
col_names = [name for _, name in sorted_items]

# =========================================
# 🔧 파일 이름 기반으로 자동 저장 경로 만들기
# =========================================
base_name = os.path.splitext(os.path.basename(file_path))[0]  # 예: 'mc'
dir_name  = os.path.dirname(file_path)

backup_path = os.path.join(dir_name, f"{base_name}_original.csv")
output_path = os.path.join(dir_name, f"{base_name}_delete_error.csv")

print(f"📂 원본 파일: {file_path}")
print(f"📦 백업 파일: {backup_path}")
print(f"💾 클린 파일: {output_path}")

# =========================================
# 1. 원본 그대로 읽기 (형식 유지용) + 백업 저장
# =========================================
raw = pd.read_csv(file_path)

raw.to_csv(backup_path, index=False, encoding='utf-8-sig')
print(f"📦 원본 파일 백업 저장 완료: {backup_path}")

# =========================================
# 1-1. 분석용 데이터셋: 특정 컬럼만 읽고 이름 통일
# =========================================
dataset = pd.read_csv(file_path, usecols=use_cols)   # 필요한 열만 읽기
dataset.columns = col_names                          # 표준 이름으로 통일

# date_time 인덱스로 설정
if 'date_time' in dataset.columns:
    dataset['date_time'] = pd.to_datetime(dataset['date_time'])
    dataset = dataset.set_index('date_time')

# 필요한 컬럼 숫자로 변환 (co2 포함)
for col in ['temperature', 'humidity', 'light', 'co2']:
    if col in dataset.columns:
        dataset[col] = pd.to_numeric(dataset[col], errors='coerce')

# 시리즈 만들기 (없는 컬럼은 NaN 시리즈 처리)
temp  = dataset['temperature'] if 'temperature' in dataset.columns else pd.Series(index=dataset.index, dtype='float')
hum   = dataset['humidity']    if 'humidity'    in dataset.columns else pd.Series(index=dataset.index, dtype='float')
light = dataset['light']       if 'light'       in dataset.columns else pd.Series(index=dataset.index, dtype='float')
co2   = dataset['co2']         if 'co2'         in dataset.columns else pd.Series(index=dataset.index, dtype='float')

# =========================================
# 2. 온도/습도 이상치 탐지 (차분 + z-score + 정상 환경 변화 제외)
# =========================================

# (1) 물리적 범위 필터
TEMP_MIN, TEMP_MAX = -10, 40
HUM_MIN,  HUM_MAX  = 0, 100

temp_physical = (temp < TEMP_MIN) | (temp > TEMP_MAX)
hum_physical  = (hum  < HUM_MIN)  | (hum  > HUM_MAX)

# (2) 차분 + z-score 기반 급변 탐지
diff_temp = temp.diff()
diff_hum  = hum.diff()

z_temp = zscore(diff_temp, nan_policy='omit')
z_hum  = zscore(diff_hum,  nan_policy='omit')

Z_THRESH = 4
cond_temp_diff = pd.Series(np.abs(z_temp) > Z_THRESH, index=dataset.index).fillna(False)
cond_hum_diff  = pd.Series(np.abs(z_hum)  > Z_THRESH, index=dataset.index).fillna(False)

print("\n[1단계] z-score 기반 급변 이상치 (정상/비정상 구분 전)")
print(f"Temperature 급변 이상치 전체: {cond_temp_diff.sum()}개")
print(f"Humidity    급변 이상치 전체: {cond_hum_diff.sum()}개")

# (3) 정상 환경 변화 패턴 (환기/히터)
normal_env = ((diff_temp < 0) & (diff_hum > 0)) | ((diff_temp > 0) & (diff_hum < 0))
normal_env = normal_env.fillna(False)

overlap_temp = cond_temp_diff & normal_env
overlap_hum  = cond_hum_diff  & normal_env

print("\n[2단계] 급변 중 정상 환경 변화(환기/히터) 패턴과 겹치는 구간")
print(f"Temp 급변 ∩ Normal Env : {overlap_temp.sum()}개")
print(f"Hum  급변 ∩ Normal Env : {overlap_hum.sum()}개")

# (4) 정상 환경 변화 제외한 비정상 급변
cond_temp_diff_adj = cond_temp_diff & ~normal_env
cond_hum_diff_adj  = cond_hum_diff  & ~normal_env

# 최종 센서 오류 (온/습)
temp_fault = (temp_physical | cond_temp_diff_adj).fillna(False)
hum_fault  = (hum_physical  | cond_hum_diff_adj).fillna(False)

print("\n[3단계] 정상 환경 변화 제외 후 최종 센서 오류")
print(f"Temperature 센서 오류 수: {temp_fault.sum()}개")
print(f"Humidity    센서 오류 수: {hum_fault.sum()}개")

# =========================================
# 3. CO₂ 이상치 탐지 (IQR + 물리 + 급격한 하락)
# =========================================
if 'co2' in dataset.columns:
    Q1, Q3 = co2.quantile([0.25, 0.75])
    IQR = Q3 - Q1
    iqr_low  = Q1 - 1.5 * IQR
    iqr_high = Q3 + 1.5 * IQR

    cond_co2_iqr  = (co2 < iqr_low) | (co2 > iqr_high)
    cond_co2_phys = (co2 < 300) | (co2 > 2000)
    diff_co2      = co2.diff()
    cond_co2_drop = diff_co2 < -500

    co2_outlier = (cond_co2_iqr | cond_co2_phys | cond_co2_drop).fillna(False)

    print("\n[3.5단계] CO₂ 이상치 탐지")
    print(f" IQR 기반 이상치    : {cond_co2_iqr.sum()}개")
    print(f" 물리적 범위 이상치 : {cond_co2_phys.sum()}개")
    print(f" 급격한 하락 이상치 : {cond_co2_drop.sum()}개")
    print(f" → CO₂ 최종 이상치 행 수: {co2_outlier.sum()}개")
else:
    co2_outlier = pd.Series(False, index=dataset.index)

# =========================================
# 4. 조도(light) 이상치 탐지 (물리 + 시간대 패턴 + 5400초과)
# =========================================
LIGHT_MIN, LIGHT_MAX = 0, 20000
LIGHT_UPPER_SUS      = 5400

light_physical = (light < LIGHT_MIN) | (light > LIGHT_MAX)

# 시간대별 평균 패턴
hourly_mean = light.groupby(light.index.hour).mean()
hour = dataset.index.hour
light_hourly_mean = pd.Series(hour, index=dataset.index).map(hourly_mean)

MEAN_EPS    = 50     # 평균이 너무 작은(밤) 시간대는 비교 제외
upper_ratio = 1.7    # 평균의 1.7배 이상
lower_ratio = 0.3    # 평균의 0.3배 이하

valid_hour = light_hourly_mean > MEAN_EPS

light_too_high_rel = valid_hour & (light > light_hourly_mean * upper_ratio)
light_too_low_rel  = valid_hour & (light < light_hourly_mean * lower_ratio)

light_upper5400 = light > LIGHT_UPPER_SUS

light_outlier = (light_physical |
                 light_too_high_rel |
                 light_too_low_rel  |
                 light_upper5400).fillna(False)

print("\n[4단계] 조도 이상치 개수")
print(f"Light 이상치 수: {light_outlier.sum()}개")

# =========================================
# 5. 원본 형식 유지 + 오류구간만 빈칸으로 만든 CSV 저장
# =========================================
cleaned = raw.copy()   # 원본 구조 유지

mask_temp_fault   = temp_fault.values
mask_hum_fault    = hum_fault.values
mask_light_fault  = light_outlier.values
mask_co2_fault    = co2_outlier.values

# ⚠️ 여기서는 원본 컬럼 이름 그대로 사용 (파일 형식 유지)
if 'temperature' in cleaned.columns:
    cleaned.loc[mask_temp_fault, 'temperature'] = np.nan

if 'humidity' in cleaned.columns:
    cleaned.loc[mask_hum_fault, 'humidity'] = np.nan

if 'light' in cleaned.columns:
    cleaned.loc[mask_light_fault, 'light'] = np.nan

if 'co2' in cleaned.columns:
    cleaned.loc[mask_co2_fault, 'co2'] = np.nan

cleaned.to_csv(output_path, index=False, encoding='utf-8-sig')

print(f"\n✅ 최종 오류 구간을 빈칸으로 처리한 CSV 저장 완료: {output_path}")
print("\n--- 열별 결측치 개수 ---")
print(cleaned.isna().sum())

# =========================================
# 6. 최종 센서 오류 시각화 (온도/습도/조도/CO₂)
# =========================================
fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True)

# (1) Temperature
axes[0].plot(temp.index, temp.values, label='Temperature', alpha=0.7)
axes[0].scatter(temp.index[temp_fault],
                temp[temp_fault],
                s=20, c='red', label='Final fault')
axes[0].set_ylabel('Temperature (°C)')
axes[0].set_title('Temperature – Final Sensor Fault Only')
axes[0].legend()

# (2) Humidity
axes[1].plot(hum.index, hum.values, label='Humidity', alpha=0.7)
axes[1].scatter(hum.index[hum_fault],
                hum[hum_fault],
                s=20, c='red', label='Final fault')
axes[1].set_ylabel('Humidity (%)')
axes[1].set_title('Humidity – Final Sensor Fault Only')
axes[1].legend()

# (3) Light
axes[2].plot(light.index, light.values, label='Light', alpha=0.7)
axes[2].scatter(light.index[light_outlier],
                light[light_outlier],
                s=15, c='red', label='Light outlier')
axes[2].set_ylabel('Light (Lux)')
axes[2].set_title('Light – Outliers (Pattern-based)')
axes[2].legend()

# (4) CO2
axes[3].plot(co2.index, co2.values, label='CO₂', alpha=0.7)
axes[3].scatter(co2.index[co2_outlier],
                co2[co2_outlier],
                s=15, c='red', label='CO₂ outlier')
axes[3].set_ylabel('CO₂ (ppm)')
axes[3].set_title('CO₂ – Outliers (IQR + Physical + Drop)')
axes[3].set_xlabel('Time')
axes[3].legend()

plt.tight_layout()
plt.show()

# =========================================
# 7. 실시간(마지막 행) 오류 감지
# =========================================
latest_raw   = raw.iloc[-1]
latest_idx   = dataset.index[-1]
latest_temp  = temp.iloc[-1]
latest_hum   = hum.iloc[-1]
latest_light = light.iloc[-1]
latest_co2   = co2.iloc[-1]

latest_temp_fault  = temp_fault.iloc[-1]
latest_hum_fault   = hum_fault.iloc[-1]
latest_light_fault = light_outlier.iloc[-1]
latest_co2_fault   = co2_outlier.iloc[-1]

print("\n================= [실시간(마지막 행) 오류 감지 결과] =================")
if 'date_time' in raw.columns:
    print(f"시각: {latest_raw['date_time']}")
else:
    print(f"시각(Index): {latest_idx}")

print(f"Temperature 값: {latest_temp}  → {'⚠️ 센서 오류' if latest_temp_fault else '✅ 정상'}")
print(f"Humidity    값: {latest_hum}   → {'⚠️ 센서 오류' if latest_hum_fault else '✅ 정상'}")
print(f"Light       값: {latest_light} → {'⚠️ 이상치' if latest_light_fault else '✅ 정상'}")
print(f"CO₂         값: {latest_co2}   → {'⚠️ 이상치' if latest_co2_fault else '✅ 정상'}")
print("====================================================================")