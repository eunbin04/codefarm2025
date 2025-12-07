# outlier_fix/predict_full.py
import pandas as pd
import joblib
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split


def retrain_model(df_full, target_col, features_cols, model_dir="outlier_fix/trained_models"):
    """
    주어진 df_full(윈도우 구간)로 target_col에 대한 모델을 재학습하고 저장.
    - df_full: 이미 보정이 반영된 최근 1개월(윈도우) 구간
    - target_col: 'Temperature' / 'Humidity' / 'Solar_Radiation'
    - features_cols: 입력 피처 리스트
    """
    required_cols = ['temp_lag_1', 'humi_lag_1', 'solar_lag_1', target_col]
    df_train_full = df_full.dropna(subset=required_cols)

    if len(df_train_full) < 100:
        print(f"[경고] {target_col} 재학습 데이터 부족 ({len(df_train_full)}행). 재학습 스킵.")
        return None

    X_train = df_train_full[features_cols]
    y_train = df_train_full[target_col]

    X_train_sub, X_val, y_train_sub, y_val = train_test_split(
        X_train, y_train, test_size=0.2, shuffle=False, random_state=42
    )

    model = lgb.LGBMRegressor(
        objective='regression',
        metric='rmse',
        n_estimators=1000,
        random_state=42,
        learning_rate=0.05,
    )

    model.fit(
        X_train_sub,
        y_train_sub,
        eval_set=[(X_val, y_val)],
        eval_metric='rmse',
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )

    model_filename = f"{model_dir}/model_{target_col}.pkl"
    joblib.dump(model, model_filename)
    print(f"[재학습 완료] {target_col} 모델 저장: {model_filename}")
    return model


def correct_outlier_df(df, temp_index, humi_index, light_index):
    """
    슬라이딩 윈도우(최근 1개월 = 44580분) + 하루(1440분) 단위 순차 보정 + 매일 재학습.

    1) 첫 결측 지점 전까지는 그대로 두고,
    2) 첫 결측 지점 기준으로:
       - 현재 인덱스를 포함하는 최근 1개월(또는 그보다 짧은) 구간을 학습 윈도우로 설정
       - 이 윈도우로 Temperature / Humidity / Solar_Radiation 모델을 재학습
       - 그 다음 하루(최대 1440행)를 순차적으로 보정
       - 하루 보정이 끝나면 윈도우를 하루 앞으로 밀고 재학습 → 다음 하루 보정
    3) 파일 끝까지 반복

    반환:
      - df_copy: 보정된 DataFrame (시간/lag 등 보조 컬럼 포함한 상태로 반환)
      - msg: 요약 메시지
    """
    cols = df.columns.tolist()
    temp_col = cols[temp_index]
    humi_col = cols[humi_index]
    light_col = cols[light_index]
    time_col = "date_time" if "date_time" in df.columns else cols[0]

    df_copy = df.copy()

    # 0. 시간 및 파생 피처
    if time_col in df_copy.columns:
        df_copy[time_col] = pd.to_datetime(df_copy[time_col], errors="coerce")
        df_copy = df_copy.sort_values(time_col).reset_index(drop=True)
        df_copy["hour"] = df_copy[time_col].dt.hour
        df_copy["minute"] = df_copy[time_col].dt.minute
    else:
        df_copy["hour"] = 0
        df_copy["minute"] = 0

    # 1. 학습용 컬럼명으로 통일
    rename_map = {
        temp_col: "Temperature",
        humi_col: "Humidity",
        light_col: "Solar_Radiation",
    }
    df_copy = df_copy.rename(columns=rename_map)

    for c in ["Temperature", "Humidity", "Solar_Radiation"]:
        df_copy[c] = pd.to_numeric(df_copy[c], errors="coerce")

    # 2. lag feature 초기화
    df_copy["temp_lag_1"] = df_copy["Temperature"].shift(1)
    df_copy["humi_lag_1"] = df_copy["Humidity"].shift(1)
    df_copy["solar_lag_1"] = df_copy["Solar_Radiation"].shift(1)

    all_analysis_cols = [
        "Temperature",
        "Humidity",
        "Solar_Radiation",
        "hour",
        "minute",
        "temp_lag_1",
        "humi_lag_1",
        "solar_lag_1",
    ]
    target_list = ["Temperature", "Humidity", "Solar_Radiation"]

    changes_made = False

    # 3. 첫 결측 지점 찾기
    first_nan_index = df_copy[df_copy[target_list].isnull().any(axis=1)].index.min()
    if pd.isna(first_nan_index):
        return df_copy, "수정할 결측치 없음"

    print(f"[보정 시작] 첫 결측 인덱스: {first_nan_index}")

    # 슬라이딩 윈도우 설정
    SAMPLE_MINUTES = 1          # 1행 = 1분
    WINDOW_DAYS = 30            # 최근 30일
    WINDOW_SIZE = WINDOW_DAYS * 24 * 60   # 30 * 24 * 60 = 43200 이지만
    # 원래 코드와 맞추려면 44580 사용 (조금 넉넉한 한 달)
    WINDOW_SIZE = 44580
    DAY_SIZE = 1440             # 1일 = 1440분

    n = len(df_copy)
    # 시작 위치를 윈도우 뒤쪽에 맞추기 위해, 가능한 한 앞에서부터 윈도우를 채움
    # (윈도우 시작 인덱스는 0이거나, first_nan_index - WINDOW_SIZE 중 큰 값)
    # 하지만 실제 학습 시점은 "보정 시작 직전까지"의 윈도우 구간이 되도록 조정
    current_start = max(0, first_nan_index - WINDOW_SIZE)
    current_index = first_nan_index

    # 4. 메인 루프: current_index부터 끝까지 하루씩 보정
    while current_index < n:
        # (1) 현재 윈도우 정의: [window_start, current_index) 구간
        #    - 윈도우 길이를 최대 WINDOW_SIZE로 제한
        window_end = current_index
        window_start = max(0, window_end - WINDOW_SIZE)
        df_window = df_copy.iloc[window_start:window_end].copy()

        if len(df_window) < 100:
            print(f"[정보] 윈도우 데이터가 너무 적어 학습 스킵 (행수={len(df_window)}).")
            # 최소 데이터가 너무 적으면, 남은 구간은 더 이상 모델을 갱신하지 않고
            # 단순히 현재 값/lag 기반으로만 처리할 수도 있지만,
            # 여기서는 추가 학습 없이 기존 모델 사용이 어렵기 때문에 break.
            break

        # (2) 윈도우 구간으로 3개 타깃 모델 재학습
        print(f"\n[재학습] 윈도우: {window_start} ~ {window_end - 1} (총 {len(df_window)}행)")
        features_for_train = [c for c in all_analysis_cols if c not in target_list]
        models = {}
        for target in target_list:
            model = retrain_model(df_window.copy(), target, features_for_train)
            if model is not None:
                models[target] = model

        if not models:
            print("[경고] 어떤 타깃도 재학습되지 않아, 이후 보정을 진행하지 않습니다.")
            break

        # (3) 이번에 보정할 하루 구간 계산
        day_end = min(current_index + DAY_SIZE, n)
        print(f"[보정] 인덱스 {current_index} ~ {day_end - 1} 하루 구간 순차 보정 시작")

        # 하루 구간 순차 보정
        for idx in range(current_index, day_end):

            # (3-1) 동적 lag 업데이트: 바로 이전 행의 최신 값 반영
            prev_idx = idx - 1
            if prev_idx >= 0:
                prev_temp = df_copy.at[prev_idx, "Temperature"]
                prev_humi = df_copy.at[prev_idx, "Humidity"]
                prev_solar = df_copy.at[prev_idx, "Solar_Radiation"]

                if pd.isna(df_copy.at[idx, "temp_lag_1"]) and not pd.isna(prev_temp):
                    df_copy.at[idx, "temp_lag_1"] = prev_temp
                if pd.isna(df_copy.at[idx, "humi_lag_1"]) and not pd.isna(prev_humi):
                    df_copy.at[idx, "humi_lag_1"] = prev_humi
                if pd.isna(df_copy.at[idx, "solar_lag_1"]) and not pd.isna(prev_solar):
                    df_copy.at[idx, "solar_lag_1"] = prev_solar

            # (3-2) 각 타깃별 결측 보정
            for target in target_list:
                if not pd.isna(df_copy.at[idx, target]):
                    continue  # 이미 값이 있으면 스킵

                model = models.get(target)
                if model is None:
                    continue

                row = df_copy.loc[idx].copy()
                features = [c for c in all_analysis_cols if c != target]

                # 동시 결측 처리: Temperature/Humidity/Solar_Radiation 결측이면 lag로 채우기 시도
                for feat in features:
                    if pd.isna(row[feat]):
                        proxy = None
                        if feat == "Temperature":
                            proxy = row["temp_lag_1"]
                        elif feat == "Humidity":
                            proxy = row["humi_lag_1"]
                        elif feat == "Solar_Radiation":
                            proxy = row["solar_lag_1"]
                        if proxy is not None and not pd.isna(proxy):
                            row[feat] = proxy

                # 여전히 NaN이 있으면 예측 불가
                if row[features].isnull().any():
                    continue

                try:
                    X_pred = np.array(row[features]).reshape(1, -1)
                    pred_value = model.predict(X_pred)[0]
                    df_copy.at[idx, target] = pred_value
                    changes_made = True
                except Exception as e:
                    print(f"[예측 실패] idx={idx}, target={target}, error={e}")

        # 하루 보정이 끝났으므로, 다음 윈도우 기준 인덱스를 하루 뒤로 이동
        current_index = day_end

    # 5. 컬럼 이름 원복
    reverse_rename = {v: k for k, v in rename_map.items()}
    df_copy = df_copy.rename(columns=reverse_rename)

    # 보조 컬럼 정리: hour, minute, lag 들 제거
    drop_cols = ['hour', 'minute', 'temp_lag_1', 'humi_lag_1', 'solar_lag_1']
    drop_cols = [c for c in drop_cols if c in df_copy.columns]
    df_copy = df_copy.drop(columns=drop_cols)

    msg = "이상치 및 결측치 보정 완료" if changes_made else "수정할 이상치 및 결측치 없음"
    return df_copy, msg