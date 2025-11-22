# cleandata_train.py
import schedule
import threading
import time
from outlier_fix.train_models import train_model
from utils import get_korea_time
import json
import os

SETTINGS_FILE = "config/settings.json"

def load_auto_train_time():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return settings.get("auto_train_time", "02:00")
    return "02:00"

scheduler_running = False
scheduler_thread = None

def job():
    train_model()
    with open("outlier_fix/train_log.txt", "a") as f:
        f.write(f"{get_korea_time().strftime('%Y-%m-%d %H:%M:%S')} (KST)\n")

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
    target_time = load_auto_train_time()
    t_hour, t_minute = target_time.split(":")
    schedule.every().day.at(f"{t_hour}:{t_minute}").do(job)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    return f"자동 학습이 시작되었습니다! ({target_time}마다 실행)"

def stop_scheduler():
    global scheduler_running
    scheduler_running = False
    schedule.clear()
    return "자동 학습이 중지되었습니다."

def manual_train():
    train_model()
    with open("outlier_fix/train_log.txt", "a") as f:
        f.write(f"{get_korea_time().strftime('%Y-%m-%d %H:%M:%S')} (KST)\n")
    return "학습이 완료되었습니다!"

def get_train_log():
    try:
        with open("outlier_fix/train_log.txt", "r") as f:
            logs = f.readlines()
        return logs[::-1]  # 최신순
    except FileNotFoundError:
        return []
