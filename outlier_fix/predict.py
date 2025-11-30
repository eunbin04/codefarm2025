# outlier_fix/predict.py
import pandas as pd
import joblib, json, os

SETTINGS_FILE = "config/settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"h_location": 3, "r_location": 4, "t_location": 1}

def correct_last_row_outlier(df: pd.DataFrame, settings=None):
    if settings is None:
        settings = load_settings()

    h_location = settings.get("h_location", 3)
    r_location = settings.get("r_location", 4)
    t_location = settings.get("t_location", 1)

    df = df.copy()
    cols = df.columns.tolist()
    timestamp_col = cols[0]

    array = [
        name
        for _, name in sorted(
            [
                (h_location, "Humidity"),
                (t_location, "Temperature"),
                (r_location, "Solar_Radiation"),
            ]
        )
    ]
    use_cols = [0, h_location, r_location, t_location]

    sub_df = df.iloc[:, use_cols].copy()
    sub_df.columns = ["Timestamp"] + array

    sub_df["Timestamp"]       = pd.to_datetime(sub_df["Timestamp"], errors="coerce")
    sub_df["Temperature"]     = pd.to_numeric(sub_df["Temperature"], errors="coerce")
    sub_df["Humidity"]        = pd.to_numeric(sub_df["Humidity"], errors="coerce")
    sub_df["Solar_Radiation"] = pd.to_numeric(sub_df["Solar_Radiation"], errors="coerce")

    sub_df["hour"]       = sub_df["Timestamp"].dt.hour
    sub_df["minute"]     = sub_df["Timestamp"].dt.minute
    sub_df["temp_lag_1"] = sub_df["Temperature"].shift(1)
    sub_df["humi_lag_1"] = sub_df["Humidity"].shift(1)
    sub_df["solar_lag_1"]= sub_df["Solar_Radiation"].shift(1)

    target_to_predict = None
    last_row_index = sub_df.index[-1]
    last_row = sub_df.loc[[last_row_index]]

    if last_row["Temperature"].isnull().any():
        target_to_predict = "Temperature"
    elif last_row["Humidity"].isnull().any():
        target_to_predict = "Humidity"
    elif last_row["Solar_Radiation"].isnull().any():
        target_to_predict = "Solar_Radiation"

    if not target_to_predict:
        return df, "보정할 이상치가 없습니다."

    try:
        model_filename = f"outlier_fix/trained_models/model_{target_to_predict}.pkl"
        model = joblib.load(model_filename)

        all_cols = [
            "Temperature", "Humidity", "Solar_Radiation",
            "hour", "minute", "temp_lag_1", "humi_lag_1", "solar_lag_1",
        ]
        features = [c for c in all_cols if c != target_to_predict]
        X_pred = last_row[features]
        predicted_value = model.predict(X_pred)[0]

        col_map = {
            "Humidity":        h_location,
            "Solar_Radiation": r_location,
            "Temperature":     t_location,
        }
        df_col_idx  = col_map[target_to_predict]
        df_col_name = cols[df_col_idx]

        df.at[last_row_index, df_col_name] = float(predicted_value)

        ts = sub_df.at[last_row_index, "Timestamp"]
        msg = f"{ts} 행, {target_to_predict}를 {predicted_value:.2f}로 보정"

        return df, msg

    except FileNotFoundError:
        return df, f"오류: '{model_filename}' 모델 파일이 없습니다. (학습 먼저 필요)"
    except Exception as e:
        return df, f"예측 중 오류 발생: {e}"
