# cleandata.py
import streamlit as st
import datetime as datetime
from outlier_fix.train_models import train_model
from outlier_fix.predict import correct_outlier
from outlier_find.find_outlier import find_outlier
from precleaning.incoding import read_csv_robust, clean_for_analysis
import schedule
import threading
import time
import pandas as pd
import sqlite3
from settings import load_settings

scheduler_running = False
scheduler_thread = None  # 백그라운드 스레드 객체

def job():
    train_model()
    with open("outlier_fix/train_log.txt", "a") as f:
        f.write(f"{datetime.datetime.now()}\n")

def run_scheduler():
    while scheduler_running:
        schedule.run_pending()
        time.sleep(1)

def start_scheduler():
    global scheduler_running, scheduler_thread
    if scheduler_running:
        st.warning("이미 자동 실행 중입니다.")
        return
    scheduler_running = True
    schedule.clear()
    
    schedule.every(1).minutes.do(job)
    # schedule.every(24).hours.do(job)   # 24시간마다 실행
    # schedule.every().day.at("01:00").do(job)   # 매일 새벽 1시에 실행

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    st.success("자동 학습이 시작되었습니다! (1분마다 반복)")

def stop_scheduler():
    global scheduler_running
    scheduler_running = False
    schedule.clear()
    st.success("자동 학습이 중지되었습니다.")

def upload_preclean():
    uploaded_file = st.file_uploader("데이터 파일 업로드", type=['csv','xlsx'])
    if uploaded_file is not None:
        # 임시 저장 경로 및 이름
        temp_path = f"temp/{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if uploaded_file.type == 'text/csv':
            df_raw, enc = read_csv_robust(temp_path)
            df_clean = clean_for_analysis(df_raw)
            enc_used = enc
        else:
            df_clean = pd.read_excel(temp_path)
            df_clean = clean_for_analysis(df_clean)
            enc_used = 'excel'

        st.write("전처리된 데이터 미리보기(끝에서 5행)")
        st.dataframe(df_clean.tail())

        # 클린 데이터를 DB에 저장
        conn = sqlite3.connect('codefarmdb.sqlite')
        df_clean.to_sql('farm_data', conn, if_exists='replace', index=False)
        conn.close()

        st.success(f"데이터가 DB에 저장되었습니다! (인코딩: {enc_used})")
        return temp_path   # 업로드한 파일 경로 반환
    else:
        return None

def show_cleandata():
    st.title("✨ 클린 데이터")

    st.markdown("---")
    st.subheader("🎓 모델 학습")

    if st.button("▶️ 수동 학습 실행"):
        with st.spinner("모델 학습 중... 잠시만 기다려주세요"):
            train_model()
        st.success("학습이 완료되었습니다!")
        with open("outlier_fix/train_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}\n")

    if st.button("🔄 자동 학습 시작"):
        start_scheduler()

    if st.button("⏹️ 자동 학습 중지"):
        stop_scheduler()

    try:
        with open("outlier_fix/train_log.txt", "r") as f:
            log_content = f.read()
        st.markdown("#### 이전 학습 실행 로그")
        st.text(log_content)
    except FileNotFoundError:
        st.info("아직 실행 로그가 없습니다.")

    st.markdown("---")
    st.subheader("🛠️ 클린 데이터 다운로드")

    # 업로드 및 파일 경로 받아오기
    file_path = upload_preclean()

    # 설정 불러오기 (경로 및 컬럼 위치 포함)
    settings = load_settings()
    location_map = {
        settings['t_location']: 'Temperature',
        settings['h_location']: 'Humidity',
        settings['r_location']: 'Solar_Radiation'
    }

    outlier_path = None
    fixed_file = None

    if file_path is not None:
        outlier_path = f"temp/outlier_{os.path.basename(file_path)}"
        fixed_file = f"temp/fixed_{os.path.splitext(os.path.basename(file_path))[0]}.xlsx"

    if st.button("보정하기"):
        if file_path is None:
            st.warning("먼저 데이터를 업로드 해 주세요.")
        else:
            with st.spinner("이상치 탐지 중... 잠시만 기다려주세요"):
                find_outlier(file_path, output_path=outlier_path, location_map=location_map)
            with st.spinner("보정 중... 잠시만 기다려주세요"):
                msg = correct_outlier(input_path=outlier_path, output_path=fixed_file, settings=settings)
            st.success("보정 작업이 완료되었습니다!")
            st.info(msg)

    if fixed_file is not None and os.path.exists(fixed_file):
        with open(fixed_file, 'rb') as f:
            data = f.read()

        st.download_button(
            label=":material/download: 클린 데이터 다운로드",
            data=data,
            file_name="clean_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    show_cleandata()
