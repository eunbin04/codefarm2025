# cleandata_train.py
import datetime
import schedule
import threading
from outlier_fix.train_models import train_model
import time

scheduler_running = False
scheduler_thread = None

def job():
    train_model()
    with open("outlier_fix/train_log.txt", "a") as f:
        f.write(f"{datetime.datetime.now()}\n")

def run_scheduler():
    global scheduler_running
    while scheduler_running:
        schedule.run_pending()
        time.sleep(1)

def start_scheduler():
    global scheduler_running, scheduler_thread
    if scheduler_running:
        return "이미 자동 실행 중입니다."
    scheduler_running = True
    schedule.clear()
    schedule.every(1).minutes.do(job)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    return "자동 학습이 시작되었습니다! (1분마다 반복)"

def stop_scheduler():
    global scheduler_running
    scheduler_running = False
    schedule.clear()
    return "자동 학습이 중지되었습니다."

def manual_train():
    train_model()
    with open("outlier_fix/train_log.txt", "a") as f:
        f.write(f"{datetime.datetime.now()}\n")
    return "학습이 완료되었습니다!"

def get_train_log():
    try:
        with open("outlier_fix/train_log.txt", "r") as f:
            log_content = f.read()
        return log_content
    except FileNotFoundError:
        return "아직 실행 로그가 없습니다."
