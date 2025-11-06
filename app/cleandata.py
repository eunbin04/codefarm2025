import streamlit as st
import datetime as datetime
from outlier_fix.train_models import train_model
import schedule
import threading
import time

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


def show_cleandata():
    st.title("📈 대시보드")

    st.markdown("---")
    
    st.markdown("### 모델 학습 시키기")

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
        st.markdown("### 이전 학습 실행 로그")
        st.text(log_content)
    except FileNotFoundError:
        st.info("아직 실행 로그가 없습니다.")

