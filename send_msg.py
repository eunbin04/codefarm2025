# send_msg.py
import sqlite3
import pandas as pd
import requests
import time
import os
import json
import qrcode
import threading
from datetime import datetime, timedelta
import numpy as np
import pytz  # ✅ 한국 시간 사용

TOKEN = "8363279994:AAHVMfjy7wxG_FmtTemoAoaXLgpWvKYtCj8"
DB_PATH = "alarms.db"
SENSOR_DB = "sensor_data.db"
DATA_DIR = "data"
CHAT_ID_FILE = os.path.join(DATA_DIR, "chat_ids.json")
SETTINGS_FILE = "config/settings.json"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
offset = None

KST = pytz.timezone("Asia/Seoul")  # ✅ 한국 시간대

# ============================================================
# 📌 settings.json 로드
# ============================================================
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "farm_name": "농가",
        "daily_stat_time": "08:24",
        "t_location": 3,
        "h_location": 2,
        "r_location": 4,
        "vpd_alert_interval_min": 10,
    }

# ============================================================
# 📌 data 폴더/ chat_ids.json 자동 생성
# ============================================================
def init_storage():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    if not os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)
    else:
        try:
            with open(CHAT_ID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                with open(CHAT_ID_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=4)
        except:
            with open(CHAT_ID_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)

# ============================================================
# 📌 chat_id 저장 / 로드
# ============================================================
def save_chat_id(chat_id):
    with open(CHAT_ID_FILE, "r", encoding="utf-8") as f:
        try:
            chat_ids = json.load(f)
            if not isinstance(chat_ids, list):
                chat_ids = []
        except:
            chat_ids = []

    if chat_id not in chat_ids:
        chat_ids.append(chat_id)
        with open(CHAT_ID_FILE, "w", encoding="utf-8") as f:
            json.dump(chat_ids, f, ensure_ascii=False, indent=4)

def load_chat_ids():
    with open(CHAT_ID_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ============================================================
# 📌 텔레그램 메시지 전송
# ============================================================
def send_message(chat_id, text, add_keyboard=False):
    url = f"{BASE_URL}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    if add_keyboard:
        payload["reply_markup"] = {
            "keyboard": [[{"text": "실시간"}]],
            "resize_keyboard": True,
            "one_time_keyboard": False,
        }

    requests.post(url, json=payload)

def broadcast(text):
    for cid in load_chat_ids():
        send_message(cid, text)

# ============================================================
# 📌 QR 코드 생성
# ============================================================
def generate_qr():
    bot_link = f"https://t.me/{get_bot_username()}?start=start"
    img = qrcode.make(bot_link)

    qr_path = os.path.join(DATA_DIR, "bot_qr.png")
    img.save(qr_path)

    print(f"QR 코드 생성 완료: {qr_path}")

# ============================================================
# 📌 봇 username 확인
# ============================================================
def get_bot_username():
    url = f"{BASE_URL}/getMe"
    res = requests.get(url).json()
    return res["result"]["username"]

# ============================================================
# 📌 실시간 버튼 → 센서 최신 행
# ============================================================
def get_latest_sensor_data():
    conn = sqlite3.connect(SENSOR_DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM measurements ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    conn.close()

    if not row:
        return "<b>📡 실시간 센서 데이터 없음</b>"

    keys = ["id", "time_str", "humidity", "temperature", "irradiance", "server_sent"]
    data = dict(zip(keys, row))

    text = (
        "<b>📡 실시간 센서 데이터</b>\n"
        "━━━━━━━━━━━\n"
        f"⏱ 시각 : {data['time_str']}\n"
        f"🌡 온도 : {data['temperature']} °C\n"
        f"💧 습도 : {data['humidity']} %\n"
        f"☀️ 일사 : {data['irradiance']} W/m²\n"
    )
    return text

# ============================================================
# 📌 새로운 알람 감지 (alarms) → 카드 스타일 포맷
# ============================================================
def get_alarm_group_by_created_at(created_at):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT time_str, alarm_type, value, status FROM alarms WHERE created_at = ? ORDER BY id;",
        conn,
        params=[created_at],
    )
    conn.close()

    if df.empty:
        return "<b>🚨 이상치/결측 알림</b>\n(해당 시각 알림 없음)"

    time_str = str(df["time_str"].iloc[0])

    lines = [
        "<b>🚨 센서 이상치·결측 발생</b>",
        "━━━━━━━━━━━",
        f"⏱ 시각 : {time_str}",
        "",
        "<b>세부 내역</b>",
    ]

    for _, row in df.iterrows():
        atype = row["alarm_type"]
        status = row["status"]
        val = row["value"]

        if status == "결측치":
            lines.append(f"• {atype} ➜ <b>결측치</b> (값 없음)")
        else:
            if pd.isna(val):
                val_str = "값 없음"
            else:
                val_str = f"{float(val):.2f}"
            lines.append(f"• {atype} ➜ {val_str} (<b>{status}</b>)")

    return "\n".join(lines)

def watch_db_changes():
    last_id = None

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query(
                "SELECT id, created_at FROM alarms ORDER BY id DESC LIMIT 1;", conn
            )
            conn.close()

            if len(df) == 0:
                time.sleep(1)
                continue

            current_id = df["id"].iloc[0]
            created_at = df["created_at"].iloc[0]

            if last_id is None:
                last_id = current_id
            elif current_id != last_id:
                last_id = current_id
                msg = get_alarm_group_by_created_at(created_at)
                broadcast(msg)

        except Exception as e:
            print("DB 감시 오류(alarms):", e)

        time.sleep(1)

# ============================================================
# 📌 VPD 솔루션 알림 감지 (vpd_alarms) + 쿨타임
# ============================================================
def get_vpd_alarm_group_by_created_at(created_at):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT time_str, vpd, temperature, humidity, solution_summary
        FROM vpd_alarms
        WHERE created_at = ?
        ORDER BY id;
        """,
        conn,
        params=[created_at],
    )
    conn.close()

    if df.empty:
        return "<b>💦 VPD 솔루션 알림</b>\n(해당 시각의 레코드 없음)"

    row = df.iloc[0]
    time_str = row["time_str"]
    vpd = row["vpd"]
    T = row["temperature"]
    H = row["humidity"]
    summary = row["solution_summary"]

    if pd.isna(vpd) or pd.isna(T) or pd.isna(H):
        state_line = "현재 상태 정보 부족 (T/RH/VPD 일부 누락)"
    else:
        state_line = f"T={T:.1f}°C, RH={H:.1f}%, VPD={vpd:.2f} kPa"

    lines = [
        "<b>💦 VPD 제어 솔루션 알림</b>",
        "━━━━━━━━━━━",
        f"⏱ 시각 : {time_str}",
        f"🔎 현재 상태 : {state_line}",
        "",
        "<b>추천 전략 요약</b>",
        f"{summary}",
    ]
    return "\n".join(lines)

def watch_vpd_db_changes():
    last_id = None

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query(
                "SELECT id, created_at FROM vpd_alarms ORDER BY id DESC LIMIT 1;",
                conn
            )
            conn.close()

            if len(df) == 0:
                time.sleep(1)
                continue

            current_id = df["id"].iloc[0]
            created_at = df["created_at"].iloc[0]

            if last_id is None:
                last_id = current_id
            elif current_id != last_id:
                last_id = current_id
                msg = get_vpd_alarm_group_by_created_at(created_at)
                broadcast(msg)

        except Exception as e:
            print("DB 감시 오류(vpd_alarms):", e)

        time.sleep(1)


# ============================================================
# 📌 하루 통계 요약 텍스트 생성 (오늘 00시~현재, KST 기준)
# ============================================================
def count_anomalies(series: pd.Series) -> int:
    if len(series) < 4:
        return 0
    Q1 = series.quantile(0.25)
    Q3 = series.quantile(0.75)
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR
    anomalies = ((series < lower) | (series > upper)).sum()
    return int(anomalies)

def generate_daily_summary_text(now_kst: datetime, settings: dict) -> str:
    """
    한국 시간(now_kst)을 기준으로
    오늘 00:00:00 ~ now_kst 까지의 데이터를 요약.
    """
    date_str = now_kst.strftime("%Y-%m-%d")
    start_ts = f"{date_str} 00:00:00"
    end_ts = now_kst.strftime("%Y-%m-%d %H:%M:%S")

    print("[DAILY] now(KST):", now_kst)
    print("[DAILY] range:", start_ts, " ~ ", end_ts)

    conn = sqlite3.connect(SENSOR_DB)
    query = """
        SELECT time_str, temperature, humidity, irradiance
        FROM measurements
        WHERE time_str >= ? AND time_str <= ?
        ORDER BY time_str ASC
    """
    df = pd.read_sql_query(query, conn, params=[start_ts, end_ts])
    conn.close()

    print("[DAILY] rows:", len(df))
    if not df.empty:
        print("[DAILY] min/max:", df["time_str"].min(), df["time_str"].max())

    if df.empty:
        return f"<b>📊 {date_str} 일일 요약</b>\n해당 날짜에 수집된 데이터가 없습니다."

    for col in ["temperature", "humidity", "irradiance"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["temperature", "humidity", "irradiance"], how="all")
    if df.empty:
        return f"<b>📊 {date_str} 일일 요약</b>\n모든 센서 값이 NaN입니다."

    lines = [
        f"<b>📊 {date_str} 일일 센서 요약</b>",
        "━━━━━━━━━━━",
        f"(기준: {start_ts} ~ {end_ts} / KST)",
    ]

    sensors = {
        "🌡 온도(°C)": "temperature",
        "💧 습도(%)": "humidity",
        "☀️ 일사(W/m²)": "irradiance",
    }

    for name_kr, col in sensors.items():
        series = df[col].dropna()
        if series.empty:
            lines.append(f"\n{name_kr}\n • 데이터 없음")
            continue

        mean = series.mean()
        max_v = series.max()
        min_v = series.min()
        std_v = series.std()
        n = len(series)
        anom = count_anomalies(series)

        lines.append(
            f"\n{name_kr}\n"
            f" • 평균: {mean:.2f}, 최대: {max_v:.2f}, 최소: {min_v:.2f}\n"
            f" • 표준편차: {std_v:.2f}, 데이터 개수: {n}, 이상치 개수: {anom}"
        )

    return "\n".join(lines)

# ============================================================
# 📌 daily_stat_time(KST)에 맞춰 하루 한 번 요약 전송
# ============================================================
def daily_stats_scheduler():
    settings = load_settings()
    farm_name = settings.get("farm_name", "농가")
    daily_time_str = settings.get("daily_stat_time", "08:24")

    try:
        daily_hour, daily_minute = map(int, daily_time_str.split(":"))
    except Exception:
        daily_hour, daily_minute = 8, 24

    last_sent_date = None

    while True:
        now_kst = datetime.now(KST)
        today = now_kst.date()

        if (last_sent_date != today) and (
            (now_kst.hour > daily_hour) or (now_kst.hour == daily_hour and now_kst.minute >= daily_minute)
        ):
            text = generate_daily_summary_text(now_kst, settings)
            header = f"<b>🏡 {farm_name} 일일 리포트</b>\n\n"
            broadcast(header + text)
            print(f"[DailyStats] {today.strftime('%Y-%m-%d')} 요약 전송 완료")
            last_sent_date = today

        time.sleep(30)

# ============================================================
# 📌 텔레그램 메시지 수신 루프
# ============================================================
def telegram_listener():
    global offset
    print("📡 Telegram listener 시작됨")

    while True:
        url = f"{BASE_URL}/getUpdates"
        params = {"timeout": 100, "offset": offset}
        res = requests.get(url, params=params).json()

        for update in res.get("result", []):
            offset = update["update_id"] + 1

            msg = update.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")

            if not chat_id:
                continue

            if text.startswith("/start"):
                save_chat_id(chat_id)
                send_message(
                    chat_id,
                    "환영합니다! 아래 버튼에서 '실시간'을 누르면 최신 센서 데이터를 볼 수 있습니다.",
                    add_keyboard=True,
                )

            if text == "실시간":
                send_message(chat_id, get_latest_sensor_data())

        time.sleep(0.5)

# ============================================================
# 📌 실행
# ============================================================
init_storage()
generate_qr()

print("Bot is running...")

threading.Thread(target=watch_db_changes, daemon=True).start()       # 이상치/결측
threading.Thread(target=watch_vpd_db_changes, daemon=True).start()   # VPD 솔루션
threading.Thread(target=daily_stats_scheduler, daemon=True).start()  # 일일 통계
threading.Thread(target=telegram_listener, daemon=True).start()

while True:
    time.sleep(10)
