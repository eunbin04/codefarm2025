# outlier_fix/train_models.py
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import joblib
import os


file_name = 'data/mc.csv' ########################

# --- 0. 엑셀 파일 불러오기 및 전처리 ---
use_cols = [0, 1, 3, 4]     ##########사용자에게 위치값을 받아와야 함
try:
    df = pd.read_csv(file_name, header=0, usecols=use_cols)
    df.columns = ['Timestamp', 'Temperature', 'Humidity', 'Solar_Radiation']
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Temperature'] = pd.to_numeric(df['Temperature'], errors='coerce')
    df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
    df['Solar_Radiation'] = pd.to_numeric(df['Solar_Radiation'], errors='coerce')

    #최근 1개월치 데이터만 학습(1분간격으로 데이터 수집할 경우)
    num_recent_rows = 44580
    if len(df) > num_recent_rows:
        df = df.tail(num_recent_rows).reset_index(drop=True)  # .tail() 사용

except FileNotFoundError:
    print(f"오류: {file_name} 파일을 찾을 수 없습니다.")
    exit()
except Exception as e:
    print(f"엑셀 파일 로드 중 오류 발생: {e}")
    exit()

# --- 1. 특징 공학 (Feature Engineering) ---
# (중요) 훈련 시에는 반드시 특징 공학(Lag, 시간)을 실행해야 합니다.
df['hour'] = df['Timestamp'].dt.hour
df['minute'] = df['Timestamp'].dt.minute

df['temp_lag_1'] = df['Temperature'].shift(1)
df['humi_lag_1'] = df['Humidity'].shift(1)
df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

# Lag 특징으로 생긴 NaN 행 제거
df = df.dropna(subset=['temp_lag_1', 'humi_lag_1', 'solar_lag_1'])
#print("특징 공학 완료.")

# --- 2.  3개 모델 순환 학습  ---

target_list = ['Temperature', 'Humidity', 'Solar_Radiation']

# (중요) 훈련 시에는 '정상 데이터'만 사용해야 하므로,
# 맨 마지막 결측치 행(테스트용)이 있다면 확실히 제거합니다.
df_train_full = df.dropna(subset=target_list)


model_dir = "outlier_fix/trained_models"
os.makedirs("outlier_fix/trained_models", exist_ok=True)


def train_model():
    for target_col in target_list:
        #print(f"\n===== {target_col} 모델 학습 시작 =====")

        # --- 3. X (특징) / y (타겟) 정의 ---
        features = [col for col in df.columns if col not in ['Timestamp', target_col]]

        X_train = df_train_full[features]
        y_train = df_train_full[target_col]

        # --- 4. LightGBM 모델 훈련 ---
        X_train_sub, X_val, y_train_sub, y_val = train_test_split(
            X_train, y_train, test_size=0.2, shuffle=False, random_state=42
        )

        model = lgb.LGBMRegressor(
            objective='regression',
            metric='rmse',
            n_estimators=1000,
            random_state=42,
            learning_rate=0.05
        )

        model.fit(
            X_train_sub,
            y_train_sub,
            eval_set=[(X_val, y_val)],
            eval_metric='rmse',
            callbacks=[lgb.early_stopping(50, verbose=False)]  # 로그 숨기기
        )

        #print(f"최적 트리 개수: {model.best_iteration_}")

        
        # (추가) 모델을 파일로 저장
        for target_col in target_list:  
            # ... (모델 학습 코드 생략)
            model_filename = f'{model_dir}/model_{target_col}.pkl'
            joblib.dump(model, model_filename)
            #print(f"===== {target_col} 모델 저장 완료 ({model_filename}) =====")

    # print("\n--- 모든 모델 학습 및 저장 완료 ---")