# outlier_fix/predict.py
import pandas as pd
import joblib
import openpyxl
import shutil

def correct_outlier():
    file_name = 'data/mc_copy.xlsx'  
    fixed_file = 'outlier_fix/fixed_datas/mc_fixed.xlsx'  
    model_dir = 'outlier_fix/trained_models'  

    # --- 내부 변수: 유동적 컬럼 위치 지정
    h_location = 3
    r_location = 4
    t_location = 1

    # 위치 변수 기준 컬럼명 정렬
    array = [name for _, name in sorted([
        (h_location, 'Humidity'),
        (t_location, 'Temperature'),
        (r_location, 'Solar_Radiation')
    ])]

    # 원본 엑셀 파일을 복사해서 fixed_file 경로에 저장
    shutil.copyfile(file_name, fixed_file)
    df = pd.read_excel(fixed_file)

    # use_cols 로 컬럼 인덱스를 유동 할당, 고정된 컬럼명 배열 적용
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

    # --- 특징 공학 및 결측치 판별 (기존 고정 리스트 유지) ---
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
            model_filename = f'{model_dir}/model_{target_to_predict}.pkl'
            model = joblib.load(model_filename)

            all_analysis_cols = ['Temperature', 'Humidity', 'Solar_Radiation',
                                 'hour', 'minute', 'temp_lag_1', 'humi_lag_1',
                                 'solar_lag_1']
            features = [col for col in all_analysis_cols if col != target_to_predict]
            X_predict = predict_df[features]
            predicted_value = model.predict(X_predict)

            # 유동적 col_map 생성, 기존 고정값 대신 위치 변수 +1 보정
            col_map = {
                'Humidity': h_location + 1,
                'Solar_Radiation': r_location + 1,
                'Temperature': t_location + 1,
            }
            excel_col = col_map.get(target_to_predict)
            excel_row = original_nan_index + 2  # 엑셀 행 위치 산출

            if excel_col is None:
                raise Exception(f"타겟 '{target_to_predict}'의 엑셀 열을 찾을 수 없습니다.")

            wb = openpyxl.load_workbook(fixed_file)
            ws = wb.active

            ws.cell(row=excel_row, column=excel_col).value = predicted_value[0]
            wb.save(fixed_file)

        except FileNotFoundError:
            print(f"오류: '{model_filename}' 모델 파일이 없습니다. (학습 먼저 실행 필요)")
        except Exception as e:
            print(f"예측 중 오류 발생: {e}")

        msg = f"{df.at[original_nan_index, 'Timestamp']} 행, '{target_to_predict}' 열에 {predicted_value[0]:.2f} 저장"
        print(msg)
        return msg

if __name__ == "__main__":
    correct_outlier()