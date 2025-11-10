# cleandata.py
import streamlit as st
import datetime as datetime
from outlier_fix.train_models import train_model
from outlier_fix.predict import correct_outlier
from precleaning.incoding import read_csv_robust, clean_for_analysis
import schedule
import threading
import time
import pandas as pd
import sqlite3
import shutil
import tempfile


scheduler_running = False  
scheduler_thread = None   # 백그라운드 스레드 객체

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
        if uploaded_file.type == 'text/csv':
            # 임시 파일에 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                shutil.copyfileobj(uploaded_file, tmp)
                tmp_path = tmp.name

            # 경로를 넘겨서 인코딩 자동감지 함수 호출
            df_raw, enc = read_csv_robust(tmp_path)
            df_clean = clean_for_analysis(df_raw)

        else:
            df_clean = pd.read_excel(uploaded_file)
            df_clean = clean_for_analysis(df_clean)
            enc = 'excel'

        st.write("전처리된 데이터 미리보기")
        st.dataframe(df_clean.head())

        # DB 저장
        conn = sqlite3.connect('codefarmdb.sqlite')
        df_clean.to_sql('farm_data', conn, if_exists='replace', index=False)
        conn.close()

        st.success(f"데이터가 DB에 저장되었습니다! (인코딩: {enc})")


def download():
    cleaned_file = 'outlier_fix/fixed_datas/mc_fixed.xlsx'
    with open(cleaned_file, 'rb') as f:
        data = f.read()

    st.download_button(
        label=":material/download: 클린 데이터 다운로드",
        data=data,
        file_name="clean_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )



def show_cleandata():
    st.title("📈 대시보드")

    st.markdown("---")
    
    st.subheader("모델 학습 시키기")

    # 수동 실행 버튼
    if st.button("수동 학습 실행"):
        with st.spinner("모델 학습 중... 잠시만 기다려주세요"):
            result = train_model()
        st.success("학습이 완료되었습니다!")
        with open("outlier_fix/train_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}\n")

    # 자동 실행 시작 버튼
    if st.button("자동 학습 시작 (1분마다)"):
        start_scheduler()

    # 자동 실행 중지 버튼
    if st.button("자동 학습 중지"):
        stop_scheduler()

    # 로그 파일 표시
    try:
        with open("outlier_fix/train_log.txt", "r") as f:
            log_content = f.read()
        st.subheader("이전 학습 실행 로그")
        st.text(log_content)
    except FileNotFoundError:
        st.info("아직 실행 로그가 없습니다.")


    st.markdown("---")

    st.subheader("클린 데이터 다운로드")
    upload_preclean()

    if st.button("보정하기"):
        msg = correct_outlier()
        st.success("보정 작업이 완료되었습니다!")
        st.text(msg)  # 추가로 보정 위치 메시지 표시
        
    download()
