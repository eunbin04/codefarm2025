# train_models_rt.py
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
import joblib
import sqlite3
import json
import os
from datetime import datetime
import pytz

SETTINGS_FILE = "config/settings.json"
SENSOR_DB_PATH = "sensor_data.db"
KST = pytz.timezone("Asia/Seoul")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"h_location": 2, "r_location": 4, "t_location": 3}

def load_data_from_db():
    """sensor_data.db에서 measurements 전부 읽어서 시간 오름차순으로 정렬"""
    conn = sqlite3.connect(SENSOR_DB_PATH)
    df = pd.read_sql("SELECT * FROM measurements ORDER BY id ASC", conn)
    conn.close()
    return df

def main():
    settings = load_settings()

    # DB에서 전체 데이터 로드
    df_raw = load_data_from_db()
    if df_raw.empty:
        print("학습 불가: sensor_data.db에 데이터가 없습니다.")
        return

    # 0번 열: time_str 기준이라고 가정 (rtdata / batch_runner와 일관성)
    # measurements 테이블 구조에 맞게 변환
    # time_str → Timestamp, 나머지는 settings의 위치를 학습 코드에서도 그대로 사용할 수도 있지만
    # 여기서는 DB 스키마에 맞춰 바로 쓰는 쪽으로 단순화 (temperature, humidity, irradiance 컬럼 존재한다고 가정)
    df = df_raw.copy()
    df["Timestamp"] = pd.to_datetime(df["time_str"], errors="coerce")
    df["Temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["Humidity"] = pd.to_numeric(df["humidity"], errors="coerce")
    df["Solar_Radiation"] = pd.to_numeric(df["irradiance"], errors="coerce")

    # 가장 최근 44,580개만 사용
    num_recent_rows = 44580
    if len(df) < num_recent_rows:
        print(f"학습 스킵: 데이터 {len(df)}개 (< {num_recent_rows})")
        return

    df = df.tail(num_recent_rows).reset_index(drop=True)

    # 1. 특징 공학
    df["hour"] = df["Timestamp"].dt.hour
    df["minute"] = df["Timestamp"].dt.minute
    df["temp_lag_1"] = df["Temperature"].shift(1)
    df["humi_lag_1"] = df["Humidity"].shift(1)
    df["solar_lag_1"] = df["Solar_Radiation"].shift(1)

    # Lag로 생긴 NaN 제거
    df = df.dropna(subset=["temp_lag_1", "humi_lag_1", "solar_lag_1"])

    target_list = ["Temperature", "Humidity", "Solar_Radiation"]
    df_train_full = df.dropna(subset=target_list)

    if df_train_full.empty:
        print("학습 스킵: 타깃 컬럼에 유효 데이터가 없습니다.")
        return

    # 모델 디렉토리 (predict.py에서 쓰는 경로와 맞춤)
    model_dir = "outlier_fix/trained_models_rt"
    os.makedirs(model_dir, exist_ok=True)

    for target_col in target_list:
        print(f"\n===== {target_col} 모델 학습 및 평가 시작 =====")

        all_cols = [
            "Temperature", "Humidity", "Solar_Radiation",
            "hour", "minute", "temp_lag_1", "humi_lag_1", "solar_lag_1"
        ]
        features = [c for c in all_cols if c != target_col]

        X_train = df_train_full[features]
        y_train = df_train_full[target_col]

        X_train_sub, X_val, y_train_sub, y_val = train_test_split(
            X_train, y_train, test_size=0.2, shuffle=False, random_state=42
        )

        model = lgb.LGBMRegressor(
            objective="regression",
            metric="rmse",
            n_estimators=1000,
            random_state=42,
            learning_rate=0.05,
            verbose=-1,
        )

        model.fit(
            X_train_sub,
            y_train_sub,
            eval_set=[(X_val, y_val)],
            eval_metric="rmse",
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

        y_pred = model.predict(X_val)
        r2 = r2_score(y_val, y_pred)

        model_filename = os.path.join(model_dir, f"model_{target_col}_rt.pkl")
        joblib.dump(model, model_filename)
        print(f"{target_col} 모델 저장 완료: {model_filename} (R²: {r2:.4f})")

    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_kst}] 모든 모델 학습 및 저장 완료!")

if __name__ == "__main__":
    main()
