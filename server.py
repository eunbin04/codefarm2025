# server.py (백엔드: 데이터 저장소 역할) --> 코드스페이스에서 실행
from flask import Flask, request, jsonify
import sqlite3

DB_PATH = 'sensor_data.db'

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

# -- DB 테이블 초기화 함수 --
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT, 
            humidity REAL,
            temperature REAL,
            irradiance REAL,
            server_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# -- 서버 시작 시 DB 테이블 생성 --
with app.app_context():
    init_db()

@app.route('/api/upload', methods=['POST'])
def upload_data():
    try:
        data = request.get_json()
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO measurements (time_str, humidity, temperature, irradiance, server_sent)
            VALUES (?, ?, ?, ?, 1)
        ''', (data['time_str'], data['humidity'], data['temperature'], data['irradiance']))
        conn.commit()
        conn.close()
        return jsonify({"msg": "Saved"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
