# outlier_fix/predict_full.py
import pandas as pd
import joblib
import numpy as np

def correct_outlier_df(df, temp_index, humi_index, light_index):
    cols = df.columns.tolist()
    temp_col = cols[temp_index]
    humi_col = cols[humi_index]
    light_col = cols[light_index]
    time_col = 'date_time' if 'date_time' in df.columns else cols[0]  # 날짜 컬럼이 있으면 활용

    # 1. 특징 생성
    df_copy = df.copy()
    if time_col in df_copy.columns:
        df_copy['hour'] = pd.to_datetime(df_copy[time_col]).dt.hour
        df_copy['minute'] = pd.to_datetime(df_copy[time_col]).dt.minute
    else:
        df_copy['hour'] = 0
        df_copy['minute'] = 0

    # Lag Feature
    df_copy[f'{temp_col}_lag_1'] = df_copy[temp_col].shift(1)
    df_copy[f'{humi_col}_lag_1'] = df_copy[humi_col].shift(1)
    df_copy[f'{light_col}_lag_1'] = df_copy[light_col].shift(1)

    # 2. 모델 로드 (파일명은 관례에 따라 조절)
    try:
        models = {
            temp_col: joblib.load(f'outlier_fix/trained_models/model_Temperature.pkl'),
            humi_col: joblib.load(f'outlier_fix/trained_models/model_Humidity.pkl'),
            light_col: joblib.load(f'outlier_fix/trained_models/model_Solar_Radiation.pkl')
        }
    except Exception as e:
        return df_copy, f"모델 로드 실패: {e}"

    analysis_cols = [temp_col, humi_col, light_col,
                     'hour', 'minute',
                     f'{temp_col}_lag_1', f'{humi_col}_lag_1', f'{light_col}_lag_1']

    target_list = [temp_col, humi_col, light_col]
    changes_made = False

    df_pred = df_copy.dropna(subset=[f'{temp_col}_lag_1', f'{humi_col}_lag_1', f'{light_col}_lag_1'])

    for target in target_list:
        nan_rows = df_pred[df_pred[target].isnull()]
        if nan_rows.empty:
            continue
        model = models.get(target)
        features = [col for col in analysis_cols if col != target]
        for idx, row in nan_rows.iterrows():
            if row[features].isnull().any():
                continue  # 입력값 결측 존재시 예측 안함
            try:
                X_pred = np.array(row[features]).reshape(1, -1)
                pred_value = model.predict(X_pred)
                df_copy.at[idx, target] = pred_value[0]
                changes_made = True
            except Exception as e:
                print(f"예측 실패: {idx}-{target}, {e}")

    msg = "모든 결측치 보정 완료" if changes_made else "수정할 결측치 없음"
    return df_copy, msg

# (아래는 모듈 실행용 샘플, 실제 서비스에서는 사용 안함)
if __name__ == "__main__":
    df = pd.read_csv("sample.csv")
    fixed, msg = correct_outlier_df(df, 1, 2, 3)
    print(msg)
    print(fixed.tail())
