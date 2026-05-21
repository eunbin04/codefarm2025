# outlier_fix/train_models.py
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import joblib
import os


def train_model(df, t_location, h_location, r_location):
    """
    DB에서 선택된 DataFrame(df)과 사용자가 입력한 인덱스(t/h/r)를 사용해
    - Temperature / Humidity / Solar_Radiation 컬럼을 매핑
    - predict_full.py 와 동일한 피처(hour, minute, lag들)를 생성
    - 최근 1개월(44580행) 데이터로 LightGBM 회귀 모델 3개 학습 후 저장
    """
    cols = df.columns.tolist()
    time_col = cols[0]  # cleandata에서 Timestamp/date_time 이 0번이라 가정

    temp_col = cols[t_location]
    humi_col = cols[h_location]
    light_col = cols[r_location]

    df_train = df.copy()

    # 1. 시간 컬럼 처리
    df_train[time_col] = pd.to_datetime(df_train[time_col], errors='coerce')
    df_train = df_train.sort_values(time_col).reset_index(drop=True)

    # 2. 학습용 표준 이름으로 매핑
    rename_map = {
        temp_col: 'Temperature',
        humi_col: 'Humidity',
        light_col: 'Solar_Radiation',
    }
    df_train = df_train.rename(columns=rename_map)

    # 3. 우선 전 컬럼을 숫자로 캐스팅 시도 (시간 컬럼 제외)
    for col in df_train.columns:
        if col != time_col:
            df_train[col] = pd.to_numeric(df_train[col], errors='coerce')
    # 주요 센서 3개는 확실히 숫자로
    df_train['Humidity'] = pd.to_numeric(df_train['Humidity'], errors='coerce')
    df_train['Solar_Radiation'] = pd.to_numeric(df_train['Solar_Radiation'], errors='coerce')
    df_train['Temperature'] = pd.to_numeric(df_train['Temperature'], errors='coerce')

    # 4. 최근 1개월치(44580행)만 사용 (1분 간격 기준)
    num_recent_rows = 44580
    if len(df_train) > num_recent_rows:
        df_train = df_train.tail(num_recent_rows).reset_index(drop=True)

    # 5. 특징 공학 (predict_full 과 동일 구조)
    df_train['hour'] = df_train[time_col].dt.hour
    df_train['minute'] = df_train[time_col].dt.minute
    df_train['temp_lag_1'] = df_train['Temperature'].shift(1)
    df_train['humi_lag_1'] = df_train['Humidity'].shift(1)
    df_train['solar_lag_1'] = df_train['Solar_Radiation'].shift(1)

    df_train = df_train.dropna(subset=['temp_lag_1', 'humi_lag_1', 'solar_lag_1'])

    # 6. 모델 학습
    target_list = ['Temperature', 'Humidity', 'Solar_Radiation']
    df_train_full = df_train.dropna(subset=target_list)

    model_dir = "outlier_fix/trained_models"
    os.makedirs(model_dir, exist_ok=True)

    for target_col in target_list:
        features = [
            col for col in df_train.columns
            if col not in [time_col, target_col]
        ]
        # 여기서 한 번 더: 피처 컬럼들은 전부 numeric 으로 강제
        df_train_full[features] = df_train_full[features].apply(
            pd.to_numeric, errors='coerce'
        )

        X_train = df_train_full[features]
        y_train = df_train_full[target_col]

        # LightGBM이 object 를 못 받으니, 남은 object 컬럼이 있으면 제거
        bad_dtypes = X_train.dtypes[X_train.dtypes == 'object'].index.tolist()
        if bad_dtypes:
            X_train = X_train.drop(columns=bad_dtypes)
            features = [f for f in features if f not in bad_dtypes]

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

    return "모델 학습 성공적으로 완료"


if __name__ == "__main__":
    # 단독 실행 시에는 df를 따로 만들어 넘겨야 함
    pass
