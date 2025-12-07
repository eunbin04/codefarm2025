# app_details/cleandata_train.py
import time
import streamlit as st
from outlier_fix.train_models import train_model
from app_details.cleandata_fixfile import process_table_df

def train_and_fix(df, t_location, h_location, r_location, timestamp_index=None):
    """
    1) 선택된 df + 인덱스로 모델 3개 학습
    2) 같은 df + 인덱스로 이상치 탐지(find_full) + 보정(predict_full)
    """
    # 1. 모델 학습
    with st.spinner("모델 학습 중..."):
        msg_train = train_model(df, t_location, h_location, r_location)

    # 2. 이상치 탐지 + 보정 (타임스탬프 전달)
    with st.spinner("이상치 탐지 및 보정 중..."):
        df_fixed, msg_fix = process_table_df(
            df,
            t_location,
            h_location,
            r_location,
            timestamp_index  # 🔴 전달
        )

    # (선택) 아주 짧은 시간 동안 상태 전환 여유를 줌
    time.sleep(0.1)

    final_msg = f"{msg_train} / {msg_fix}"
    return df_fixed, final_msg
