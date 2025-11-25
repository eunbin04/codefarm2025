# server.py (백엔드: 데이터 저장소 역할)
from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('sensor_data.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# [초기 설정] DB 테이블 만들기
with app.app_context():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_str TEXT, 
            humidity REAL,
            temperature REAL,
            irradiance REAL
        )
    ''')
    conn.commit()
    conn.close()

# [핵심] 아두이노 데이터를 받아서 DB에 저장하는 API
@app.route('/api/upload', methods=['POST'])
def upload_data():
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO measurements (time_str, humidity, temperature, irradiance)
            VALUES (?, ?, ?, ?)
        ''', (data['time_str'], data['humidity'], data['temperature'], data['irradiance']))
        conn.commit()
        conn.close()
        
        return jsonify({"msg": "Saved"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    # 5000번 포트에서 데이터 수신 대기
    app.run(host='0.0.0.0', port=5000)