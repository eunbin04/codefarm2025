import sqlite3
import pandas as pd
import requests
import time
import os
import json
import qrcode
import threading


TOKEN = "8363279994:AAHVMfjy7wxG_FmtTemoAoaXLgpWvKYtCj8"
DB_PATH = "alarms.db"
SENSOR_DB = "sensor_data.db"
DATA_DIR = "data"
CHAT_ID_FILE = os.path.join(DATA_DIR, "chat_ids.json")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
offset = None


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
# 📌 chat_id 저장
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
            "one_time_keyboard": False
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
        return "<b>📡 센서 데이터 없음</b>"

    keys = ["id", "time_str", "humidity", "temperature", "irradiance", "server_sent"]
    data = dict(zip(keys, row))

    col_width = max(len(k) for k in data)
    block = "".join(f"{k.ljust(col_width)} : {v}\n" for k, v in data.items())

    return "<b>📡 최신 센서 데이터</b>\n<pre>" + block + "</pre>"


# ============================================================
# 📌 새로운 알람 감지 → 같은 created_at 묶어 전송
# ============================================================
def get_alarm_group_by_created_at(created_at):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM alarms WHERE created_at = ? ORDER BY id;",
        conn,
        params=[created_at]
    )
    conn.close()

    blocks = []
    for _, row in df.iterrows():
        rd = row.to_dict()
        w = max(len(k) for k in rd)
        block = "".join(f"{k.ljust(w)} : {v}\n" for k, v in rd.items())
        blocks.append(f"<pre>{block}</pre>")

    return "<b>🚨 결측치 or 이상치 발생</b>\n" + "\n".join(blocks)


def watch_db_changes():
    last_id = None

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT id, created_at FROM alarms ORDER BY id DESC LIMIT 1;", conn)
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
            print("DB 감시 오류:", e)

        time.sleep(1)


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
                send_message(chat_id, "환영합니다! '실시간'을 누르면 최신 센서 데이터를 볼 수 있습니다.", add_keyboard=True)

            if text == "실시간":
                send_message(chat_id, get_latest_sensor_data())

        time.sleep(0.5)


# ============================================================
# 📌 실행
# ============================================================
init_storage()
generate_qr()

print("Bot is running...")

threading.Thread(target=watch_db_changes, daemon=True).start()
threading.Thread(target=telegram_listener, daemon=True).start()

while True:
    time.sleep(10)
