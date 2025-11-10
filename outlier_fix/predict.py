# outlier_fix/predict.py
import pandas as pd
import joblib
import openpyxl
import json
import os

SETTINGS_FILE = "config/settings.json"
file_name = 'data/outliers/priva_delete_error.csv'
fixed_file = 'outlier_fix/fixed_datas/priva_fixed.xlsx'


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings
    else:
        # 기본값
        return {
            "h_location": 3,
            "r_location": 4,
            "t_location": 1,
        }


def correct_outlier():
    settings = load_settings()
    h_location = settings.get('h_location', 3)
    r_location = settings.get('r_location', 4)
    t_location = settings.get('t_location', 1)

    # CSV → 엑셀 변환
    try:
        df = pd.read_csv(file_name)
        df.to_excel(fixed_file, index=False)
    except Exception as e:
        print(f"파일 변환 실패: {e}")

        
    # 컬럼 위치 기준 이름 정렬
    array = [name for _, name in sorted([
        (h_location, 'Humidity'),
        (t_location, 'Temperature'),
        (r_location, 'Solar_Radiation')
    ])]

    use_cols = [0, h_location, r_location, t_location]

    try:
        df = pd.read_excel(fixed_file, header=0, usecols=use_cols)
        df.columns = ['Timestamp'] + array
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Temperature'] = pd.to_numeric(df['Temperature'], errors='coerce')
        df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
        df['Solar_Radiation'] = pd.to_numeric(df['Solar_Radiation'], errors='coerce')
    except FileNotFoundError:
        print(f"오류: {fixed_file} 파일을 찾을 수 없습니다.")
        exit()
    except Exception as e:
        print(f"엑셀 파일 로드 중 오류 발생: {e}")
        exit()

    df['hour'] = df['Timestamp'].dt.hour
    df['minute'] = df['Timestamp'].dt.minute
    df['temp_lag_1'] = df['Temperature'].shift(1)
    df['humi_lag_1'] = df['Humidity'].shift(1)
    df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

    predict_df = None
    target_to_predict = None
    original_nan_index = None

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
        original_nan_index = last_row_index

    if target_to_predict and predict_df is not None:
        try:
            model_filename = f'outlier_fix/trained_models/model_{target_to_predict}.pkl'
            model = joblib.load(model_filename)

            all_analysis_cols = ['Temperature', 'Humidity', 'Solar_Radiation',
                                 'hour', 'minute', 'temp_lag_1', 'humi_lag_1',
                                 'solar_lag_1']
            features = [col for col in all_analysis_cols if col != target_to_predict]
            X_predict = predict_df[features]
            predicted_value = model.predict(X_predict)

            # 열 위치는 엑셀 기준 (헤더 포함해서 +1, 엑셀 행 기준 +2 보정)
            col_map = {
                'Humidity': h_location + 1,
                'Solar_Radiation': r_location + 1,
                'Temperature': t_location + 1,
            }
            excel_col = col_map.get(target_to_predict)
            excel_row = original_nan_index + 2

            if excel_col is None:
                raise Exception(f"타겟 '{target_to_predict}'의 엑셀 열을 찾을 수 없습니다.")

            wb = openpyxl.load_workbook(fixed_file)
            ws = wb.active
            ws.cell(row=excel_row, column=excel_col).value = predicted_value[0]
            wb.save(fixed_file)
            msg = f"{df.at[original_nan_index, 'Timestamp']} 행, {target_to_predict} 열에 {predicted_value[0]:.2f} 저장"
            print(msg)
            return msg

        except FileNotFoundError:
            print(f"오류: '{model_filename}' 모델 파일이 없습니다. (학습 먼저 실행 필요)")
        except Exception as e:
            print(f"예측 중 오류 발생: {e}")


if __name__ == "__main__":
    correct_outlier()