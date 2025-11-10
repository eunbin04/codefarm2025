# outlier_fix/predict_full.py
import pandas as pd
import joblib
import openpyxl

file_name = 'data/mc_copy.xlsx'  
h_location = 3
r_location = 4
t_location = 1

array = [name for _, name in sorted([
    (h_location, 'Humidity'),
    (t_location, 'Temperature'),
    (r_location, 'Solar_Radiation')
])]

# (사용자 정의) 읽어올 열 인덱스
use_cols = [0, h_location,r_location, t_location]
# (사용자 정의) 실제 엑셀 저장 위치
col_map = {
    'Humidity': h_location + 1,
    'Solar_Radiation': r_location + 1,
    'Temperature': t_location + 1,
}

# --- 0. 엑셀 파일 불러오기 (Pandas) ---
try:
    df = pd.read_excel(file_name, header=0, usecols=use_cols)
    df.columns = ['Timestamp']+array
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
    df['Solar_Radiation'] = pd.to_numeric(df['Solar_Radiation'], errors='coerce')
    df['Temperature'] = pd.to_numeric(df['Temperature'], errors='coerce')
except FileNotFoundError:
    print(f"오류: {file_name} 파일을 찾을 수 없습니다.")
    exit()
except Exception as e:
    print(f"엑셀 파일 로드 중 오류 발생: {e}")
    exit()

# --- 1. 특징 공학 (Feature Engineering) ---
# 예측에 필요한 특징을 전체 df에 대해 생성합니다.
df['hour'] = df['Timestamp'].dt.hour
df['minute'] = df['Timestamp'].dt.minute
df['temp_lag_1'] = df['Temperature'].shift(1)
df['humi_lag_1'] = df['Humidity'].shift(1)
df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

# Lag 특징 생성으로 인한 첫 행 NaN은 예측에서 제외 (학습 때도 제외했으므로)
df = df.dropna(subset=['temp_lag_1', 'humi_lag_1', 'solar_lag_1'])

# --- 2. 모델 및 엑셀 파일 '먼저' 로드하기 ---
# 속도를 위해 모델과 엑셀 워크북을 '한 번만' 엽니다.
try:
    models = {
        'Temperature': joblib.load('model_Temperature.pkl'),
        'Humidity': joblib.load('model_Humidity.pkl'),
        'Solar_Radiation': joblib.load('model_Solar_Radiation.pkl')
    }
    # (openpyxl) 엑셀 파일 열기 (쓰기 전용)
    wb = openpyxl.load_workbook(file_name)
    ws = wb.active
except FileNotFoundError as e:
    print(f"오류: 모델 파일 또는 {file_name}을(를) 찾을 수 없습니다. {e}")
    exit()
except Exception as e:
    print(f"모델/파일 로드 중 오류: {e}")
    exit()

# 학습에 사용된 전체 특징 리스트 정의
all_analysis_cols = ['Temperature', 'Humidity', 'Solar_Radiation',
                     'hour', 'minute', 'temp_lag_1', 'humi_lag_1',
                     'solar_lag_1']

target_list = ['Temperature', 'Humidity', 'Solar_Radiation']
changes_made = False  # 수정 사항이 있는지 확인하는 깃발

# --- 3. '모든 결측치'를 찾아 반복 보정 ---

for target_to_predict in target_list:

    # (1) 현재 타겟(예: 'Temperature')에 결측치가 있는 '모든 행'을 찾습니다.
    nan_rows = df[df[target_to_predict].isnull()]

    if nan_rows.empty:
        continue  # 결측치가 없으면 다음 타겟(습도)으로 넘어감

    # (2) 결측치가 있다면, 필요한 모델과 특징 리스트를 준비합니다.
    model = models.get(target_to_predict)
    features = [col for col in all_analysis_cols if col != target_to_predict]
    excel_col = col_map.get(target_to_predict)

    if model is None or excel_col is None:
        print(f"경고: {target_to_predict}의 모델 또는 엑셀 열 정보가 없습니다. 건너뜁니다.")
        continue

    # (3) (★핵심★) 결측치가 있는 '각 행'을 순회하며 예측/수정
    for original_nan_index, row_data in nan_rows.iterrows():
        try:
            # (pandas 인덱스로 엑셀 행 번호 계산)
            excel_row = original_nan_index + 2  # (헤더 1행 + 0-index 1)

            # (예측에 필요한 특징 준비)
            X_predict = row_data[features].values.reshape(1, -1)

            # (예측)
            predicted_value = model.predict(X_predict)

            # (★수정★) '파일 저장'이 아닌 '메모리'에 있는 엑셀 객체(ws)에 값을 씁니다.
            ws.cell(row=excel_row, column=excel_col).value = predicted_value[0]

            changes_made = True  # 수정했다고 표시

        except Exception as e:
            print(f"오류: {original_nan_index}행 ({target_to_predict}) 보정 실패: {e}")

# --- 4.'마지막에 한 번만' 저장 ---
if changes_made:
    try:
        wb.save(file_name)
    except Exception as e:
        print(f"오류: {file_name} 저장 실패. {e}")
# else:
# print("수정할 결측치가 없습니다.")