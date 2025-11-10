# outlier_fix/predict.py
import pandas as pd
import joblib
import openpyxl


def correct_outlier():
    file_name = 'data/mc.csv'
    fixed_file = 'outlier_fix/fixed_datas/mc_fixed.xlsx'

    df = pd.read_csv(file_name)
    df.to_excel(fixed_file, index=False)


    # --- 0. 엑셀 파일 불러오기 및 전처리 ---
    use_cols = [0, 1, 2, 3] ############사용자에게 위치값 받아와야 함
    try:
        df = pd.read_excel(fixed_file, header=0, usecols=use_cols)
        df.columns = ['Timestamp', 'Temperature', 'Humidity', 'Solar_Radiation']
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

    # --- 1. 특징 공학 (Feature Engineering) ---
    # (중요) 예측 시에도 '학습 때와 똑같은' 특징을 만들어야 함
    df['hour'] = df['Timestamp'].dt.hour
    df['minute'] = df['Timestamp'].dt.minute

    df['temp_lag_1'] = df['Temperature'].shift(1)
    df['humi_lag_1'] = df['Humidity'].shift(1)
    df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

    # (주의) Lag 특징으로 첫 행이 NaN이 될 수 있으나,
    # 우리는 '마지막 행'만 예측할 것이므로 삭제(dropna)하지 않아도 됨

    # --- 2. 결측치 확인 및 조건부 예측 ---

    predict_df = None
    target_to_predict = None
    original_nan_index = None # 결측치의 pandas 인덱스 (예: 44579)

    # (1) 마지막 행에서 결측치(NaN)가 있는지 확인
    last_row_index = df.index[-1]
    last_row = df.loc[[last_row_index]] # pandas 인덱스로 마지막 행 참조

    if last_row['Temperature'].isnull().any():
        target_to_predict = 'Temperature'
    elif last_row['Humidity'].isnull().any():
        target_to_predict = 'Humidity'
    elif last_row['Solar_Radiation'].isnull().any():
        target_to_predict = 'Solar_Radiation'

    if target_to_predict:
        predict_df = last_row
        original_nan_index = last_row_index # 결측치의 pandas 인덱스 저장

    # (2) 결측치가 있다면, 해당 모델을 로드하여 예측
    if target_to_predict and predict_df is not None:
        try:
            # --- 3. X (특징) / y (타겟) 정의 ---
            model_filename = f'outlier_fix/trained_models/model_{target_to_predict}.pkl'

            # (수정) 훈련된 모델 로드
            model = joblib.load(model_filename)

            # (수정) 특징(X) 정의
            # 특징 리스트를 고정하지 않고, 학습(train) 때와 동일한 로직으로 만듭니다.
            # (1) 학습/예측에 사용될 '모든' 잠재적 특징/타겟 리스트를 정의
            all_analysis_cols = ['Temperature', 'Humidity', 'Solar_Radiation',
                                'hour', 'minute', 'temp_lag_1', 'humi_lag_1',
                                'solar_lag_1']

            # (2) 이 리스트에서 '현재 타겟'만 제외하여 특징(features)을 생성
            features = [col for col in all_analysis_cols if col != target_to_predict]

            # (수정) 예측할 데이터(X_predict)는 '마지막 행'의 특징(features)
            X_predict = predict_df[features]

            # --- 5. 결측치 예측 (보정) ---
            predicted_value = model.predict(X_predict)

            # --- 6. (★수정★) 'openpyxl'을 사용해 원본 파일의 '해당 셀'만 수정 ---

            # (1) 엑셀의 '열' 위치 찾기 (A=1, B=2, C=3, D=4, E=5)
            col_map = {
                'Temperature': 2,
                'Humidity': 4,
                'Solar_Radiation': 5
            }   ############사용자에게 위치값 받아와야 함
            excel_col = col_map.get(target_to_predict)

            # (2) 엑셀의 '행' 위치 찾기 (헤더 1행 + 데이터 인덱스)
            # pandas 인덱스 0 = 엑셀 2행
            # pandas 인덱스 44579 = 엑셀 44581행
            excel_row = original_nan_index + 2

            if excel_col is None:
                raise Exception(f"타겟 '{target_to_predict}'의 엑셀 열을 찾을 수 없습니다.")

            # (3) 엑셀 파일 열기, 수정, 저장
            wb = openpyxl.load_workbook(fixed_file)
            ws = wb.active  # (또는 wb['시트이름'])

            # (4) '쏙' 하고 값 집어넣기
            ws.cell(row=excel_row, column=excel_col).value = predicted_value[0]

            # (5) 파일 저장
            wb.save(fixed_file)
            msg = f"{excel_row}행, {excel_col}열에 {predicted_value[0]:.2f} 저장"
            print(msg)  # 터미널 출력용
            return msg

        except FileNotFoundError:
            print(f"오류: '{model_filename}' 모델 파일이 없습니다. (학습 먼저 실행 필요)")
        except Exception as e:
            print(f"예측 중 오류 발생: {e}")
        else:
            # 결측치가 없으면 아무것도 안 함
            pass

if __name__ == '__main__':
    correct_outlier()