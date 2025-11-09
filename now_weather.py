import math
import requests
import pandas as pd
from datetime import datetime, timedelta

# ===================== 1. 위경도 -> 격자(nx, ny) =====================

def latlon_to_xy(lat, lon):
    RE = 6371.00877  # 지구 반경(km)
    GRID = 5.0       # 격자 간격(km)
    SLAT1 = 30.0
    SLAT2 = 60.0
    OLON = 126.0
    OLAT = 38.0
    XO = 43
    YO = 136

    DEGRAD = math.pi / 180.0

    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon

    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi

    theta *= sn

    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def pty_to_desc(pty):
    """강수 형태 코드 → 한국어 설명"""
    mapping = {
        0: "강수 없음",
        1: "비",
        2: "비/눈",
        3: "눈",
        5: "빗방울",
        6: "빗방울/눈날림",
        7: "눈날림"
    }
    return mapping.get(pty, f"코드 {pty}")


def deg_to_dir(deg):
    """풍향(도) → 16방위 문자열"""
    if pd.isna(deg):
        return "정보 없음"
    deg = float(deg) % 360
    dirs = [
        "북", "북북동", "북동", "동북동", "동",
        "동남동", "남동", "남남동", "남",
        "남남서", "남서", "서남서", "서",
        "서북서", "북서", "북북서"
    ]
    idx = int((deg + 11.25) // 22.5) % 16
    return dirs[idx]


# ===================== 2. 설정 =====================

SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"  # 디코딩키 그대로

# 온실 위경도 (실제 좌표로 수정)
LAT = 36.1234
LON = 127.5678

nx, ny = latlon_to_xy(LAT, LON)
print(f"격자 좌표(nx, ny): {nx}, {ny}")

# 발표 기준시각 (현재 - 40분, 정시)
now = datetime.now()
base_time = (now - timedelta(minutes=40)).strftime("%H00")
base_date = now.strftime("%Y%m%d")
print("base_date:", base_date, "base_time:", base_time)

BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

params = {
    "serviceKey": SERVICE_KEY,
    "pageNo": 1,
    "numOfRows": 100,
    "dataType": "JSON",
    "base_date": base_date,
    "base_time": base_time,
    "nx": nx,
    "ny": ny,
}

# ===================== 3. API 호출 =====================

response = requests.get(BASE_URL, params=params)
print("HTTP status:", response.status_code)

data = response.json()

items = data["response"]["body"]["items"]["item"]
df = pd.DataFrame(items)

# ===================== 4. 가로로 펼치기(pivot) =====================

df_pivot = df.pivot(
    index=["baseDate", "baseTime", "nx", "ny"],
    columns="category",
    values="obsrValue"
).reset_index()

# datetime 생성
df_pivot["datetime"] = pd.to_datetime(
    df_pivot["baseDate"] + df_pivot["baseTime"],
    format="%Y%m%d%H%M"
)

# 가장 최신 한 줄 선택 (어차피 한 줄일 가능성이 크지만 안전하게)
latest = df_pivot.sort_values("datetime").iloc[-1]

# 숫자 변환
def to_float(val):
    try:
        return float(val)
    except:
        return None

t1h = to_float(latest.get("T1H"))
reh = to_float(latest.get("REH"))
rn1 = to_float(latest.get("RN1"))
wsd = to_float(latest.get("WSD"))
vec = to_float(latest.get("VEC"))
pty = latest.get("PTY")
pty = int(pty) if pty is not None and str(pty).isdigit() else 0

pty_desc = pty_to_desc(pty)
wind_dir = deg_to_dir(vec)

dt_str = latest["datetime"].strftime("%Y-%m-%d %H:%M")

# ===================== 5. 요약 출력 =====================

summary = (
    f"[{dt_str}] 현재 기준\n"
    f"- 기온: {t1h}℃\n"
    f"- 습도: {reh}%\n"
    f"- 강수: {pty_desc}"
)

if rn1 is not None:
    summary += f" (최근 1시간 강수량 {rn1}mm)"

summary += f"\n- 풍속: {wsd} m/s, 풍향: {wind_dir}"
if vec is not None:
    summary += f" ({vec}°)"

print("\n===== 현재 기상 요약 =====")
print(summary)
