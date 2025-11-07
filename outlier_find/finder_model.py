# finder_model.py
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tensorflow
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, RepeatVector, TimeDistributed
from tensorflow.keras.callbacks import EarlyStopping
import os


# --- 1. 환경 설정 및 파일 경로 ---
file_path = r"data/exdata.csv"
output_directory = r"outlier_find/outliers"  
output_file_name = 'exdata_outlier_nan_added.csv'
output_path = os.path.join(output_directory, output_file_name)

SEQUENCE_LENGTH = 30
sensors = ['temperature', 'humidity', 'light']

# --- 2. 데이터 로드 및 전처리 ---
try:
    df_raw = pd.read_csv(file_path, quoting=3, skipinitialspace=True)
except FileNotFoundError:
    print(f"Error: File not found: {file_path}")
    exit()

df_raw.columns = df_raw.columns.str.replace('"', '').str.strip()
target_cols = ['date_time'] + sensors
df = df_raw[target_cols].copy()
df['date_time'] = pd.to_datetime(df['date_time'].astype(str).str.replace('"', '').str.strip())
for col in sensors:
    df[col] = df[col].astype(str).str.replace('"', '').str.strip().replace('', np.nan).astype(float)

# 훈련 데이터셋 (결측치 제거)
df_train = df.dropna(subset=sensors).reset_index(drop=True)

# Min/Max 값 저장 및 공유
min_max_values = pd.DataFrame(
    {'Min': df_train[sensors].min().values, 'Max': df_train[sensors].max().values},
    index=sensors
)
print("\n--- 1. 센서별 Min/Max 값 ---")
print(min_max_values)


# --- 3. LSTM Autoencoder 모델 정의 (1개 특징 입력용) ---
def create_lstm_autoencoder_1d(seq_len, latent_dim=15):
    # 특징 개수는 항상 1 (해당 센서 데이터만 사용)
    model = Sequential([
        # Encoder
        LSTM(units=64, activation='relu', input_shape=(seq_len, 1), return_sequences=True),
        LSTM(units=32, activation='relu', return_sequences=False),
        # Bottleneck (Latent Space)
        Dense(latent_dim, activation='relu'),
        # Decoder
        RepeatVector(seq_len),
        LSTM(units=32, activation='relu', return_sequences=True),
        LSTM(units=64, activation='relu', return_sequences=True),
        TimeDistributed(Dense(1))  # 각 시점마다 1개의 특징 복원
    ])
    model.compile(optimizer='adam', loss='mse')
    return model


# 4. 시퀀스 생성 함수 (1개 특징용)
def create_sequences_1d(data, seq_len):
    sequences = []
    # data 형태는 (N, 1)이 되어야 함
    for i in range(len(data) - seq_len + 1):
        seq = data[i:(i + seq_len)]
        sequences.append(seq)
    return np.array(sequences)


# 전체 데이터 시퀀스 변환 함수 (패딩 포함, 1개 특징용)
def create_sequences_with_padding_1d(data, seq_len):
    # data 형태는 (N, 1)이 되어야 함
    sequences = []
    padding = np.zeros((seq_len - 1, 1))
    padded_data = np.concatenate((padding, data), axis=0)
    for i in range(len(data)):
        seq = padded_data[i:(i + seq_len)]
        sequences.append(seq)
    return np.array(sequences)


# --- 5. 3개 모델 개별 훈련 및 임계값 계산 ---
models = {}
scalers = {}
thresholds = {}
total_anomalies_count = 0
df_final = df.copy()

early_stopping = EarlyStopping(
    monitor='val_loss',
    patience=5,
    restore_best_weights=True
)

print("\n--- 2. 센서별 모델 훈련 및 임계값 설정 시작 ---")

for sensor in sensors:
    print(f"\n[모델 훈련 시작] 센서: {sensor.capitalize()}")

    # 5-1. 스케일러 생성 및 훈련 데이터 준비
    scaler = MinMaxScaler()
    train_data_1d = df_train[[sensor]].values
    scaled_train_data = scaler.fit_transform(train_data_1d)

    # 5-2. 시퀀스 데이터 생성
    X_train_sequences_1d = create_sequences_1d(scaled_train_data, SEQUENCE_LENGTH)

    # 5-3. 모델 생성 및 훈련
    model = create_lstm_autoencoder_1d(SEQUENCE_LENGTH)
    model.fit(
        X_train_sequences_1d,
        X_train_sequences_1d,
        epochs=50,
        batch_size=128,
        validation_split=0.1,
        shuffle=False,
        callbacks=[early_stopping],
        verbose=0  # 훈련 과정을 숨김
    )

    # 5-4. 훈련 손실 계산 및 임계값 설정
    train_predictions = model.predict(X_train_sequences_1d, verbose=0)
    # Loss: (시퀀스 길이, 특징 개수)인 축 (1, 2)에 대해 평균을 내어 시퀀스별 Loss 계산
    train_loss = np.mean(np.square(X_train_sequences_1d - train_predictions), axis=(1, 2))

    # 99th Percentile 임계값 설정
    threshold = np.percentile(train_loss, 99)
    thresholds[sensor] = threshold
    print(f"  -> Threshold (99th Percentile): {threshold:.8f}")

    models[sensor] = model
    scalers[sensor] = scaler

# --- 6. 전체 데이터셋에 대한 이상치 탐지 및 NaN 변환 ---
print("\n--- 3. 전체 데이터셋 이상치 탐지 및 NaN 처리 ---")

for sensor in sensors:
    model = models[sensor]
    scaler = scalers[sensor]
    threshold = thresholds[sensor]

    # 6-1. 전체 데이터 준비 및 스케일링
    full_data_1d = df[[sensor]].values

    # NaN이 포함된 원본 데이터의 스케일링 (NaN은 스케일링되지 않음)
    # NaN은 float64로 존재하므로 MinMaxScaler는 이를 무시하고 나머지 값만 변환함
    scaled_full_data = scaler.transform(full_data_1d)

    # 6-2. 전체 데이터를 시퀀스로 변환
    X_full_sequences_1d = create_sequences_with_padding_1d(scaled_full_data, SEQUENCE_LENGTH)

    # 6-3. 재구성 오차 계산
    full_predictions = model.predict(X_full_sequences_1d, verbose=0)
    full_loss = np.mean(np.square(X_full_sequences_1d - full_predictions), axis=(1, 2))

    # 6-4. 이상치 판별 및 NaN 처리
    is_anomaly = full_loss > threshold
    anomaly_indices = np.where(is_anomaly)[0]

    # 해당 센서 컬럼만 NaN으로 변환
    df_final.loc[anomaly_indices, sensor] = np.nan

    total_anomalies_count += len(anomaly_indices)
    print(f"  -> {sensor.capitalize()} 센서에서 {len(anomaly_indices)}개의 이상치가 판별되어 NaN 처리되었습니다.")

print(f"\n총 {total_anomalies_count}번의 이상치 판별이 이루어졌습니다 (중복 포함).")

# --- 7. 최종 파일 저장 및 공유 ---
os.makedirs(output_directory, exist_ok=True)
df_final.to_csv(output_path, index=False)

print(f"\n--- 4. 최종 결과 파일 저장 및 공유 ---")
print(f"이상치가 NaN으로 변환된 최종 파일: {output_path}")
print("이제 이 파일을 데이터 보정(복원) 및 VPD 계산 팀과 공유할 수 있습니다.")
print(f"Min/Max 값도 함께 전달하여 역정규화에 사용할 수 있도록 하세요.")
