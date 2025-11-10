# outlier_fix/train_models.py
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import joblib
import os
import json

SETTINGS_FILE = "config/settings.json"
file_name = 'data/mc.csv'
copy_file = 'data/mc_copy.xlsx'


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings
    else:
        # 설정 파일 없으면 기본값 반환
        return {
            "h_location": 3,
            "r_location": 4,
            "t_location": 1,
        }

def train_model():
    settings = load_settings()
    h_location = settings.get('h_location', 3)
    r_location = settings.get('r_location', 4)
    t_location = settings.get('t_location', 1)

    # CSV → 엑셀 변환
    try:
        df = pd.read_csv(file_name)
        df.to_excel(copy_file, index=False)
    except Exception as e:
        print(f"파일 변환 실패: {e}")


    array = [name for _, name in sorted([
        (h_location, 'Humidity'),
        (t_location, 'Temperature'),
        (r_location, 'Solar_Radiation')
    ])]

    # --- 0. 데이터 불러오기 및 전처리 ---
    use_cols = [0, h_location, r_location, t_location]
    try:
        # CSV 대신 CSV 파일 그대로 유지, 단 usecols 인덱스 적용 (pandas read_csv에 usecols 인덱스 가능)
        df = pd.read_excel(copy_file, header=0, usecols=use_cols)
        df.columns = ['Timestamp'] + array  # 위치 변수 기반 동적 컬럼명 지정

        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
        df['Solar_Radiation'] = pd.to_numeric(df['Solar_Radiation'], errors='coerce')
        df['Temperature'] = pd.to_numeric(df['Temperature'], errors='coerce')

        # 최근 1개월치 데이터만 학습(1분 간격 데이터 기준)
        num_recent_rows = 44580
        if len(df) > num_recent_rows:
            df = df.tail(num_recent_rows).reset_index(drop=True)

    except FileNotFoundError:
        print(f"오류: {copy_file} 파일을 찾을 수 없습니다.")
        exit()
    except Exception as e:
        print(f"데이터 로드 중 오류 발생: {e}")
        exit()

    # --- 1. 특징 공학 (Feature Engineering) ---
    df['hour'] = df['Timestamp'].dt.hour
    df['minute'] = df['Timestamp'].dt.minute
    df['temp_lag_1'] = df['Temperature'].shift(1)
    df['humi_lag_1'] = df['Humidity'].shift(1)
    df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

    # NaN 생긴 행 제거
    df = df.dropna(subset=['temp_lag_1', 'humi_lag_1', 'solar_lag_1'])

    # --- 2. 모델 학습 ---
    target_list = ['Temperature', 'Humidity', 'Solar_Radiation']
    df_train_full = df.dropna(subset=target_list)

    model_dir = "outlier_fix/trained_models"
    os.makedirs("outlier_fix/trained_models", exist_ok=True)

    for target_col in target_list:
        features = [col for col in df.columns if col not in ['Timestamp', target_col]]
        X_train = df_train_full[features]
        y_train = df_train_full[target_col]

        if X_train.empty or y_train.empty:
            print(f"[경고] {target_col} 학습용 데이터 부족, 학습 스킵")
            continue

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
            X_train_sub, y_train_sub,
            eval_set=[(X_val, y_val)],
            eval_metric='rmse',
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )

        model_filename = f'{model_dir}/model_{target_col}.pkl'
        joblib.dump(model, model_filename)
        # print(f"{target_col} 모델 저장 완료 ({model_filename})")

# print("모든 모델 학습 및 저장 완료")

if __name__ == "__main__":
    train_model()
