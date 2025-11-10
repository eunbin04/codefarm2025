import pandas as pd

# ─────────────────────────────
# 통합 솔루션 함수
# ─────────────────────────────
def give_solution(col, val_a, val_b, temp=None, hum=None, light=None):
    diff = val_b - val_a

    # 온도 단일 판단
    if "temp" in col.lower():
        temp_diff = diff
        if temp_diff < -1:
            return f"{val_a:.1f}℃에서 {val_b:.1f}℃로 낮추기 위해 환기 또는 차광 조치를 취하세요."
        elif temp_diff > 1:
            return f"{val_a:.1f}℃에서 {val_b:.1f}℃로 높이기 위해 난방 장치를 조정하세요."
        else:
            return "온도가 목표 범위에 근접합니다."

    # 습도 단일 판단
    elif "hum" in col.lower():
        hum_diff = diff
        if hum_diff < -3:
            return f"습도를 {val_a:.1f}%에서 {val_b:.1f}%로 낮추기 위해 제습이나 환기를 강화하세요."
        elif hum_diff > 3:
            return f"습도를 {val_a:.1f}%에서 {val_b:.1f}%로 높이기 위해 관수나 가습을 고려하세요."
        else:
            return "습도 상태가 목표치와 유사합니다."

    # 광도 단일 판단
    elif "light" in col.lower():
        light_diff = diff
        if light_diff < -50:
            return f"광도를 {val_a:.0f}→{val_b:.0f} µmol/m²/s로 낮추기 위해 차광막을 조정하세요."
        elif light_diff > 50:
            return f"광도를 {val_a:.0f}→{val_b:.0f} µmol/m²/s로 높이기 위해 조명 강도를 늘리세요."
        else:
            return "광도가 목표 수준에 가깝습니다."

    # 복합 판단 (온도+습도+광도)
    if temp is not None and hum is not None and light is not None:
        temp_diff = temp - val_a
        hum_diff = hum - val_a
        light_diff = light - val_a

        # 예시: 온도+광 복합
        if temp_diff > 2 and light_diff > 100:
            return "온도가 높고 광도가 과도합니다. 차광막을 닫고 미스트를 가동하세요."
        elif temp_diff > 2 and light_diff < -100:
            return "온도는 높지만 광이 부족합니다. 환기로 냉각하되, 보조조명을 켜세요."
        elif temp_diff < -2 and hum_diff < -5:
            return "온도와 습도가 모두 낮습니다. 난방과 가습을 병행하세요."

    return "특이한 변화 없음."

# ─────────────────────────────
# 파일 입력
# ─────────────────────────────
file_a = 'data/priva_original_backup.csv'
file_b = 'outlier_fix/fixed_datas/priva_fixed.xlsx'

try:
    data_a = pd.read_csv(file_a)
    data_b = pd.read_excel(file_b)
except FileNotFoundError:
    print("⚠️ 파일 경로를 확인하세요.")
    exit()

last_a = data_a.iloc[-1]
last_b = data_b.iloc[-1]

common_cols = [col for col in data_a.columns if col in data_b.columns]
if not common_cols:
    print("⚠️ 두 파일 간 공통 컬럼이 없습니다.")
    exit()

# ─────────────────────────────
# 비교 수행 및 솔루션 출력 (조치 필요 시만)
# ─────────────────────────────
print("\n📊 [A → B 상태 전환을 위한 솔루션]")

for col in common_cols:
    try:
        val_a = float(last_a[col])
        val_b = float(last_b[col])

        if pd.isna(val_a) or pd.isna(val_b):
            continue

        # 단일 또는 복합 판단
        if "temp" in col.lower():
            solution = give_solution(col, val_a, val_b,
                                     temp=val_b,
                                     hum=last_b.get("hum", None),
                                     light=last_b.get("light", None))
            unit = "℃"
        elif "hum" in col.lower():
            solution = give_solution(col, val_a, val_b)
            unit = "%"
        elif "light" in col.lower():
            solution = give_solution(col, val_a, val_b)
            unit = "µmol/m²/s"
        else:
            continue  # 특이한 변화 없음 → 출력 생략

        # 💡 솔루션이 실제로 조치를 안내하는 문장일 때만 출력
        if solution not in ["온도가 목표 범위에 근접합니다.",
                            "습도 상태가 목표치와 유사합니다.",
                            "광도가 목표 수준에 가깝습니다.",
                            "특이한 변화 없음."]:
            print(f"{col}: 현재 {val_a:.2f}{unit} → 목표 {val_b:.2f}{unit} → 💡 {solution}")

    except ValueError:
        continue
