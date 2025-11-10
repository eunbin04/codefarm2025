# outlier_fix/predict.py
import pandas as pd
import joblib
import openpyxl
import json
import os

SETTINGS_FILE = "config/settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings
    else:
        return {
            "h_location": 3,
            "r_location": 4,
            "t_location": 1,
        }

def correct_outlier(input_path, output_path, settings=None):
    if settings is None:
        settings = load_settings()

    h_location = settings.get('h_location', 3)
    r_location = settings.get('r_location', 4)
    t_location = settings.get('t_location', 1)

    try:
        df = pd.read_csv(input_path)
        df.to_excel(output_path, index=False)
    except Exception as e:
        print(f"파일 변환 실패: {e}")
        return f"파일 변환 실패: {e}"

    array = [name for _, name in sorted([
        (h_location, 'Humidity'),
        (t_location, 'Temperature'),
        (r_location, 'Solar_Radiation')
    ])]

    use_cols = [0, h_location, r_location, t_location]

    try:
        df = pd.read_excel(output_path, header=0, usecols=use_cols)
        df.columns = ['Timestamp'] + array
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Temperature'] = pd.to_numeric(df['Temperature'], errors='coerce')
        df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
        df['Solar_Radiation'] = pd.to_numeric(df['Solar_Radiation'], errors='coerce')
    except FileNotFoundError:
        return f"오류: {output_path} 파일을 찾을 수 없습니다."
    except Exception as e:
        return f"엑셀 파일 로드 오류: {e}"

    df['hour'] = df['Timestamp'].dt.hour
    df['minute'] = df['Timestamp'].dt.minute
    df['temp_lag_1'] = df['Temperature'].shift(1)
    df['humi_lag_1'] = df['Humidity'].shift(1)
    df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

    target_to_predict = None
    last_row_index = df.index[-1]
    last_row = df.loc[[last_row_index]]

    if last_row['Temperature'].isnull().any():
        target_to_predict = 'Temperature'
    elif last_row['Humidity'].isnull().any():
        target_to_predict = 'Humidity'
    elif last_row['Solar_Radiation'].isnull().any():
        target_to_predict = 'Solar_Radiation'

    if target_to_predict:
        predict_df = last_row
        try:
            model_filename = f'outlier_fix/trained_models/model_{target_to_predict}.pkl'
            model = joblib.load(model_filename)

            all_analysis_cols = ['Temperature', 'Humidity', 'Solar_Radiation',
                                'hour', 'minute', 'temp_lag_1', 'humi_lag_1',
                                'solar_lag_1']
            features = [col for col in all_analysis_cols if col != target_to_predict]
            X_predict = predict_df[features]
            predicted_value = model.predict(X_predict)

            col_map = {
                'Humidity': h_location + 1,
                'Solar_Radiation': r_location + 1,
                'Temperature': t_location + 1,
            }
            excel_col = col_map.get(target_to_predict)
            excel_row = last_row_index + 2

            wb = openpyxl.load_workbook(output_path)
            ws = wb.active
            ws.cell(row=excel_row, column=excel_col).value = predicted_value[0]
            wb.save(output_path)
            msg = f"{df.at[last_row_index, 'Timestamp']} 행, {target_to_predict} 열에 {predicted_value[0]:.2f} 저장"
            print(msg)
            return msg

        except FileNotFoundError:
            return f"오류: '{model_filename}' 모델 파일이 없습니다. (학습 먼저 실행 필요)"
        except Exception as e:
            return f"예측 중 오류 발생: {e}"
    else:
        return "보정할 이상치가 없습니다."

if __name__ == "__main__":
    correct_outlier('data/outliers/priva_delete_error.csv', 'outlier_fix/fixed_datas/priva_fixed.xlsx')
