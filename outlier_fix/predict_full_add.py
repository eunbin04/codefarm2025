import pandas as pd
import joblib
import openpyxl
import lightgbm as lgb
from sklearn.model_selection import train_test_split

def retrain_model(df_full, target_col, features_cols):
    # Lag 특징으로 생긴 NaN 행 제거 및 타겟 결측치 제거
    # 특징 공학(Lag)은 이미 df_full을 만들기 전에 완료됨
    df_train_full = df_full.dropna(subset=['temp_lag_1', 'humi_lag_1', 'solar_lag_1', target_col])

    if len(df_train_full) < 100:
        print(f"경고: {target_col} 학습 데이터가 부족합니다 ({len(df_train_full)} 행). 재학습을 건너뜜니다.")
        return None

    # 2. X, y 정의
    X_train = df_train_full[features_cols]
    y_train = df_train_full[target_col]

    # 3. 데이터 분리 (훈련 데이터의 20%를 검증 데이터로 사용)
    X_train_sub, X_val, y_train_sub, y_val = train_test_split(
        X_train, y_train, test_size=0.2, shuffle=False, random_state=42
    )

    # 4. 모델 훈련
    model = lgb.LGBMRegressor(
        objective='regression',
        metric='rmse',
        n_estimators=1000,
        random_state=42,
        learning_rate=0.05
    )

    model.fit(
        X_train_sub,
        y_train_sub,
        eval_set=[(X_val, y_val)],
        eval_metric='rmse',
        callbacks=[lgb.early_stopping(50, verbose=False)]
    )

    # 5. 모델 저장
    model_filename = f'model_{target_col}.pkl'
    joblib.dump(model, model_filename)

    print(f"✅ {target_col} 모델이 최신 데이터로 재학습 및 저장되었습니다.")
    return model

file_name = '미기후(2025-10-03-11.2).xlsx'  ########################
h_location = 3
r_location = 4
t_location = 1

array = [name for _, name in sorted([
    (h_location, 'Humidity'),
    (t_location, 'Temperature'),
    (r_location, 'Solar_Radiation')
])]

# (사용자 정의) 읽어올 열 인덱스
use_cols = [0, h_location, r_location, t_location]
# (사용자 정의) 실제 엑셀 저장 위치
col_map = {
    'Humidity': h_location + 1,
    'Solar_Radiation': r_location + 1,
    'Temperature': t_location + 1,
}

# --- 0. 엑셀 파일 불러오기 ---
try:
    df = pd.read_excel(file_name, header=0, usecols=use_cols)
    df.columns = ['Timestamp'] + array
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

# --- 1. 특징 공학 (초기화) ---
df['hour'] = df['Timestamp'].dt.hour
df['minute'] = df['Timestamp'].dt.minute
df['temp_lag_1'] = df['Temperature'].shift(1)
df['humi_lag_1'] = df['Humidity'].shift(1)
df['solar_lag_1'] = df['Solar_Radiation'].shift(1)

# --- 2. 모델 및 엑셀 파일 로드 ---
try:
    models = {
        'Temperature': joblib.load('model_Temperature.pkl'),
        'Humidity': joblib.load('model_Humidity.pkl'),
        'Solar_Radiation': joblib.load('model_Solar_Radiation.pkl')
    }
    wb = openpyxl.load_workbook(file_name)
    ws = wb.active
except Exception as e:
    print(f"모델/파일 로드 중 오류: {e}")
    exit()

all_analysis_cols = ['Temperature', 'Humidity', 'Solar_Radiation',
                     'hour', 'minute', 'temp_lag_1', 'humi_lag_1',
                     'solar_lag_1']

target_list = ['Temperature', 'Humidity', 'Solar_Radiation']
changes_made = False

# ================================================================
# --- 3. 순차적 연속 보정 및 하루 단위 재학습 로직 ---
# ================================================================

# 학습 주기 설정 (1분 간격 데이터 기준)
LEARNING_INTERVAL = 1440  # 1일 = 24시간 * 60분
NUM_RECENT_ROWS = 44580  # 1개월치 데이터
last_learning_index = 0  # 마지막 학습이 이루어진 인덱스

# 결측치가 하나라도 있는 첫 번째 행의 인덱스를 찾습니다.
first_nan_index = df[df[target_list].isnull().any(axis=1)].index.min()

if pd.isna(first_nan_index):
    print("결측치가 없습니다.")
    pass

print(f"첫 결측 행 (인덱스 {first_nan_index})부터 순차 보정을 시작합니다...")

# [수정] last_learning_index를 첫 결측 행의 인덱스로 초기화합니다.
last_learning_index = first_nan_index

# 첫 결측치부터 데이터프레임의 끝까지 모든 행을 순회합니다.
for index in range(first_nan_index, len(df)):

    # ----------------------------------------------------
    # 재학습 조건 체크 (하루(1440분)가 지났는가?)
    # ----------------------------------------------------
    if (index - last_learning_index) >= LEARNING_INTERVAL:
        print(f"\n--- {index}번째 행: 하루({LEARNING_INTERVAL}분) 보정 완료. 재학습 시작. ---")

        # 1. 고품질 데이터 추출
        # 보정된 값이 df에 반영되어 있으므로, 현재까지의 df 데이터가 고품질 데이터입니다.
        start_index = max(0, index - NUM_RECENT_ROWS)
        df_high_quality = df.iloc[start_index:index].copy()

        # 2. 모든 타겟 모델 재학습 및 업데이트
        if len(df_high_quality) > 0:
            features = [col for col in all_analysis_cols if col not in target_list]
            for target_to_retrain in target_list:
                updated_model = retrain_model(df_high_quality.copy(), target_to_retrain, features)
                # 재학습이 성공하면 models 딕셔너리에 최신 모델을 업데이트
                if updated_model is not None:
                    models[target_to_retrain] = updated_model

        # 마지막 학습 인덱스를 현재 인덱스로 업데이트
        last_learning_index = index
        print(f"재학습 완료. 다음 학습은 {index + LEARNING_INTERVAL}번째 행 이후에 진행됩니다.")

    # -------------------------------------------------------
    # [핵심 2] 동적 Lag 업데이트 및 예측
    # -------------------------------------------------------

    # 1. 이전 행(index-1)이 존재하는지 확인
    prev_index = index - 1

    if prev_index in df.index:
        # 2. 이전 행의 최신 값 가져오기 (방금 채워진 값 포함)
        prev_temp = df.at[prev_index, 'Temperature']
        prev_humi = df.at[prev_index, 'Humidity']
        prev_solar = df.at[prev_index, 'Solar_Radiation']

        # 3. 현재 행의 Lag 컬럼이 비어있다면 업데이트
        if pd.isna(df.at[index, 'temp_lag_1']) and not pd.isna(prev_temp):
            df.at[index, 'temp_lag_1'] = prev_temp

        if pd.isna(df.at[index, 'humi_lag_1']) and not pd.isna(prev_humi):
            df.at[index, 'humi_lag_1'] = prev_humi

        if pd.isna(df.at[index, 'solar_lag_1']) and not pd.isna(prev_solar):
            df.at[index, 'solar_lag_1'] = prev_solar

    # 타겟 변수 순회 및 예측
    for target_to_predict in target_list:

        # 현재 타겟이 결측치인지 확인
        if pd.isna(df.at[index, target_to_predict]):

            # models 딕셔너리에는 최신 재학습된 모델이 들어있습니다.
            model = models.get(target_to_predict)
            excel_col = col_map.get(target_to_predict)

            if model is None or excel_col is None:
                continue

            # 입력 데이터 준비 (업데이트된 Lag 포함)
            input_data = df.loc[index].copy()

            # [동시 결측 처리]
            features = [col for col in all_analysis_cols if col != target_to_predict]

            for feat in features:
                if pd.isna(input_data[feat]):
                    proxy = None
                    if feat == 'Temperature':
                        proxy = input_data['temp_lag_1']
                    elif feat == 'Humidity':
                        proxy = input_data['humi_lag_1']
                    elif feat == 'Solar_Radiation':
                        proxy = input_data['solar_lag_1']

                    if proxy is not None and not pd.isna(proxy):
                        input_data[feat] = proxy

            # Lag 데이터조차 없다면 예측 불가 -> 건너뜀
            if input_data[features].isnull().any():
                continue

            try:
                # 예측
                X_predict = input_data[features].values.reshape(1, -1)
                predicted_value = model.predict(X_predict)[0]

                # 1. 엑셀 객체(ws)에 쓰기
                excel_row = index + 2
                ws.cell(row=excel_row, column=excel_col).value = predicted_value

                # 2. [중요] 데이터프레임(df) 즉시 업데이트
                df.at[index, target_to_predict] = predicted_value

                changes_made = True

            except Exception as e:
                print(f"오류: {index}행 {target_to_predict} 보정 실패: {e}")

# --- 4. 저장 ---
if changes_made:
    try:
        save_name = file_name.replace('.xlsx', '_correction.xlsx')
        wb.save(save_name)
        print(f"성공: {save_name} 파일로 저장되었습니다.")
    except Exception as e:
        print(f"오류: 저장 실패. {e}")
else:
    print("수정할 결측치가 없습니다.")