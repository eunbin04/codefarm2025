# utils.py
from datetime import datetime
from zoneinfo import ZoneInfo

def get_korea_time():
    return datetime.now(ZoneInfo("Asia/Seoul"))