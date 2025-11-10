# solution.py
import os
import glob
import pandas as pd

# 선택 사항: chardet 있으면 인코딩 추정에 사용, 없으면 그냥 넘어감
try:
    import chardet
except ImportError:
    chardet = None


# ✅ 원본 CSV들이 있는 폴더
BASE_PATH = "/content/drive/MyDrive/middle_project/중간평가_분석파일"

# ✅ 클린 CSV들을 저장할 폴더 (원하면 다른 경로로 변경 가능)
OUTPUT_DIR = "/content/drive/MyDrive/middle_project/중간평가_분석파일_clean"

# ✅ 시도해볼 인코딩 후보들
TRY_ENCODINGS = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']



def guess_encoding(path, n_bytes=200000):
    """chardet가 있으면 파일 일부를 보고 인코딩 추정, 없으면 None."""
    if chardet is None:
        return None
    with open(path, "rb") as f:
        raw = f.read(n_bytes)
    result = chardet.detect(raw)
    return result.get("encoding")


def read_csv_robust(path):
    """
    여러 인코딩으로 읽어보고,
    ???, � 같은 깨진 문자 비율이 가장 낮은 결과를 선택.
    전부 애매하면 그나마 나은 걸 쓰고, 최악이면 utf-8 + replace로 강제 로드.
    """
    tried = []
    enc_guess = guess_encoding(path)

    if enc_guess:
        try_order = [enc_guess] + [e for e in TRY_ENCODINGS if e != enc_guess]
    else:
        try_order = TRY_ENCODINGS[:]

    best_df = None
    best_enc = None
    best_bad = 1.0
    last_err = None

    for enc in try_order:
        if enc in tried:
            continue
        tried.append(enc)

        try:
            df = pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
            continue

        # 컬럼명 + 첫 행을 샘플로 가져와서 깨짐 정도 확인
        text_sample = " ".join(map(str, list(df.columns)[:30]))
        if len(df) > 0:
            text_sample += " " + " ".join(map(str, df.iloc[0].astype(str).tolist()))

        # ???, � 비율 계산
        bad = (text_sample.count('?') + text_sample.count('�')) / max(len(text_sample), 1)

        # 거의 안 깨졌으면 바로 확정
        if bad < 0.01:
            return df, enc

        # 그 외에는 "현재까지 중에 제일 덜 깨진 후보"로 저장
        if bad < best_bad:
            best_bad = bad
            best_df = df
            best_enc = enc

    # 그래도 읽힌 게 하나라도 있으면 그것 사용
    if best_df is not None:
        if best_bad > 0.1:
            print(f"[경고] {os.path.basename(path)}: 인코딩이 완벽하진 않을 수 있음 (깨짐 비율 {best_bad:.2f}), 사용 enc={best_enc}")
        return best_df, best_enc

    # 전부 실패하면 utf-8 + replace로 강제 로드 (깨진 글자는 �로 들어갈 수 있음)
    try:
        df = pd.read_csv(path, encoding="utf-8", encoding_errors="replace")
    except Exception as e:
        raise RuntimeError(f"{os.path.basename(path)}: CSV 로드 실패. 마지막 오류: {e}")
    print(f"[경고] {os.path.basename(path)}: 모든 인코딩 시도 실패 → utf-8 + replace 로 강제 로드. 마지막 오류: {last_err}")
    return df, "utf-8(replace)"


def clean_for_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    - 컬럼명 양쪽 공백 제거
    - 'Unnamed: 0' 같은 덤프 인덱스 컬럼 제거
    - 공백/빈 문자열만 있는 셀 → NaN(결측)으로 표시
    """
    # 1. 컬럼명 정리
    df.columns = [str(c).strip() for c in df.columns]

    # 2. Unnamed* 컬럼 제거
    drop_cols = [c for c in df.columns if str(c).startswith("Unnamed")]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    # 3. 공백 또는 탭 등만 있는 값들을 결측으로 처리
    df = df.replace(r'^\s*$', pd.NA, regex=True)

    return df


def make_clean_csvs(base_path: str = BASE_PATH,
                    output_dir: str = OUTPUT_DIR,
                    output_encoding: str = "utf-8-sig"):
    """
    base_path 안 모든 .csv 파일을:
    - 인코딩 자동 판별/시도해서 로드
    - 기본 클린 처리 (컬럼명 정리, Unnamed 제거, 공백→NaN)
    - output_dir 에 `{원본이름}_clean.csv` 로 저장
    """
    # ✅ 출력 폴더 생성
    os.makedirs(output_dir, exist_ok=True)

    csv_files = glob.glob(os.path.join(base_path, "*.csv"))
    if not csv_files:
        print(f"[알림] '{base_path}' 에서 CSV 파일을 찾지 못했습니다.")
        return

    for path in csv_files:
        filename = os.path.basename(path)
        name, ext = os.path.splitext(filename)

        # 이미 _clean 으로 끝나는 파일은 스킵
        if name.endswith("_clean"):
            continue

        try:
            df_raw, enc = read_csv_robust(path)
            df_clean = clean_for_analysis(df_raw)

            clean_name = f"{name}_clean{ext}"
            clean_path = os.path.join(output_dir, clean_name)

            df_clean.to_csv(clean_path, index=False, encoding=output_encoding)

            print(
                f"[완료] {filename} -> {clean_name} 저장 ({output_dir}) | "
                f"읽은 enc={enc} | shape={df_clean.shape}"
            )
        except Exception as e:
            print(f"[오류] {filename} 처리 실패: {e}")


# ✅ 이 한 줄만 실행하면 BASE_PATH 안 CSV → OUTPUT_DIR에 *_clean.csv 생성
make_clean_csvs()



bdf = pd.read_csv("/content/drive/MyDrive/middle_project/중간평가_분석파일_clean미기후(2025-10.3-11.2)", encoding="utf-8-sig")

import pandas as pd
import numpy as np
import requests
from datetime import datetime

# ================== 설정 ==================
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"
STN_ID = "146"  # 전주 ASOS 지점번호
GROWTH_CSV_PATH = "/content/drive/MyDrive/middle_project/중간평가_분석파일/미기후(2025-10.3-11.2).csv"  #여기에 파일 넣으면 환경 솔루션 해주는거!!! 다른 거는 안 만져두 됨!

VPD_MIN = 0.66  # 최솟값
VPD_MAX = 0.95   # 최댓값

ASOS_DAILY_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"


# ================== 1. ASOS 일별 평균 습도 + 일사 가져오기 ==================
def fetch_asos_daily_with_rh_rad(stn_id, start_date, end_date, service_key):
    start_dt = start_date.replace("-", "")
    end_dt = end_date.replace("-", "")

    params = {
        "serviceKey": service_key,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "DAY",
        "startDt": start_dt,
        "endDt": end_dt,
        "stnIds": stn_id,
        "pageNo": "1",
        "numOfRows": "999",
    }

    # 요청 타임아웃을 30초로 늘려줍니다.
    resp = requests.get(ASOS_DAILY_URL, params=params, timeout=100)
    print("[ASOS] HTTP 상태 코드:", resp.status_code)
    resp.raise_for_status()

    js = resp.json()
    items = js["response"]["body"]["items"]["item"]

    df = pd.DataFrame(items)

    # 사용할 후보 컬럼: 날짜, 평균습도, 일사/일조
    base_cols = ["tm", "avgRhm"]
    for c in base_cols:
        if c not in df.columns:
            raise RuntimeError(f"[ASOS] 응답에 {c} 컬럼이 없습니다. 실제 응답 구조를 print해서 확인해봐야 합니다.")

    # 일사량 컬럼 우선순위: sumGsr(일사) > sumSsHr(일조시간) > 없음
    rad_col = None
    if "sumGsr" in df.columns:
        rad_col = "sumGsr"
    elif "sumSsHr" in df.columns:
        rad_col = "sumSsHr"

    use_cols = base_cols + ([rad_col] if rad_col else [])
    df = df[use_cols].copy()

    df.rename(columns={"tm": "date", "avgRhm": "ext_humidity"}, inplace=True)

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ext_humidity"] = pd.to_numeric(df["ext_humidity"], errors="coerce")

    if rad_col:
        df["ext_solar"] = pd.to_numeric(df[rad_col], errors="coerce")
    else:
        # 일사 정보 없으면 NaN
        df["ext_solar"] = np.nan

    print("[ASOS] 일수:", len(df))
    return df


# ================== 2. 생육데이터 + VPD ==================
def load_growth_and_calc_vpd(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]

    # 시간 컬럼
    time_candidates = ["date_time", "일시", "수집일", "관측일시", "time", "datetime"]
    time_col = next((c for c in time_candidates if c in df.columns), None)
    if time_col is None:
        raise RuntimeError(f"[GROWTH] 시간 컬럼을 찾을 수 없습니다. 현재 컬럼: {list(df.columns)}")

    df[time_col] = pd.to_datetime(df[time_col])
    df["date"] = df[time_col].dt.date

    # 내부 온도/습도 컬럼
    temp_candidates = ["내부-내부온도", "내부온도", "temperature", "내부 온도"]
    hum_candidates  = ["내부-내부습도", "내부습도", "humidity", "내부 습도"]

    temp_col = next((c for c in temp_candidates if c in df.columns), None)
    hum_col  = next((c for c in hum_candidates if c in df.columns), None)

    if temp_col is None or hum_col is None:
        raise RuntimeError(
            f"[GROWTH] 내부 온도/습도 컬럼 없음\n"
            f"온도 후보: {temp_candidates}\n습도 후보: {hum_candidates}\n"
            f"현재 컬럼: {list(df.columns)}"
        )

    # VPD 계산
    def calc_vpd_kpa(temp_c, rh):
        es = 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))
        ea = es * (rh / 100.0)
        return es - ea

    df["vpd_kpa"] = calc_vpd_kpa(df[temp_col], df[hum_col])

    # 주간 여부
    rad_candidates = ["내부-내부일사량", "내부-일사", "일사량", "solar", "radiation"]
    rad_col = next((c for c in rad_candidates if c in df.columns), None)

    if rad_col is not None:
        df["is_daytime"] = df[rad_col] > 0
    else:
        df["is_daytime"] = df[time_col].dt.hour.between(6, 18)

    return df, time_col, temp_col, hum_col


# ================== 3. 메시지 생성 파이프라인 ==================
def run_vpd_control():
    # 1) 내부 데이터
    df, time_col, temp_col, hum_col = load_growth_and_calc_vpd(GROWTH_CSV_PATH)

    # 2) ASOS 외부 평균습도 + 일사
    start_date = df["date"].min().strftime("%Y-%m-%d")
    end_date   = df["date"].max().strftime("%Y-%m-%d")

    df_asos = fetch_asos_daily_with_rh_rad(
        stn_id=STN_ID,
        start_date=start_date,
        end_date=end_date,
        service_key=SERVICE_KEY,
    )

    # 3) 날짜 기준 merge
    merged = pd.merge(df, df_asos, on="date", how="left")

    # 4) 제어 메시지 로직
    def control_msg(row):
        if not row["is_daytime"]:
            return ""

        vpd = row["vpd_kpa"]
        in_h = row[hum_col]                         # 내부 습도
        ext_h = row.get("ext_humidity", np.nan)     # 외부 평균 상대습도
        ext_solar = row.get("ext_solar", np.nan)    # 외부 일사 (일사량 or 일조시간 합계)

        # ① VPD 낮음 → 보광 (+ 외부가 더 건조하면 환기도 같이 추천)
        if vpd < VPD_MIN:
            if not np.isnan(ext_h) and ext_h < in_h:
                return "보광이 필요합니다! / 환기를 추천드립니다!"
            return "보광이 필요합니다!"

        # ② VPD 높음 → 일사량 기준으로 차광 vs 환풍기
        if vpd > VPD_MAX:
            # 일사 정보 없으면: 열/습 제거 위해 환풍 위주
            if np.isnan(ext_solar):
                return "환풍기를 돌리세요!"

            # 🔹 임계값 예시:
            # - ext_solar가 sumGsr(일사량 MJ/m² 등) 또는 sumSsHr(일조시간)일 수 있음.
            # - 값이 어느 정도 이상이면 '햇빛 영향 크다' 보고 차광 우선.
            #   여기서는 편의로 5 이상이면 차광, 미만이면 환풍으로 분기.
            if ext_solar >= 5:
                return "차광을 하세요"
            else:
                return "환풍기를 돌리세요!"

        # ③ 그 외: 목표 범위(0.66~0.95)에 가까운 경우 → 별도 액션 없음
        return ""

    merged["control_message"] = merged.apply(control_msg, axis=1)
    msg_df = merged[merged["control_message"] != ""]
    return msg_df, time_col, hum_col, merged


# ================== 4. 출력 ==================
if __name__ == "__main__":
    msg_df, time_col, hum_col, merged = run_vpd_control()

    if msg_df.empty:
        print("메시지가 나온 row가 없습니다.")
    else:
        # 메시지 발생 구간 상위 50개만 보기
        print(
            msg_df[[time_col, hum_col, "vpd_kpa", "ext_humidity", "ext_solar", "control_message"]]
            .head(50)
            .to_string(index=False)
        )

import pandas as pd
import numpy as np
import requests
from datetime import datetime

# 미기후

# ================== 설정 ==================
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"  # 시연 때 실제 키 or 잘못 넣어도, 실패 시 자동으로 가짜데이터 사용
STN_ID = "146"  # 전주 ASOS 지점번호
# GROWTH_CSV_PATH = "/content/drive/MyDrive/middle_project/프리바(2024-11.18-11.26)_clean_correction.csv"
GROWTH_CSV_PATH = "/content/drive/MyDrive/middle_project/프리바(2024-11.18-11.26)_clean.csv"


VPD_MIN = 0.66  # 최솟값
VPD_MAX = 0.95  # 최댓값

ASOS_DAILY_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"


# ================== 1. ASOS 일별 평균 습도 + 일사 가져오기 ==================
def fetch_asos_daily_with_rh_rad(stn_id, start_date, end_date, service_key):
    start_dt = start_date.replace("-", "")
    end_dt = end_date.replace("-", "")

    params = {
        "serviceKey": service_key,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "DAY",
        "startDt": start_dt,
        "endDt": end_dt,
        "stnIds": stn_id,
        "pageNo": "1",
        "numOfRows": "999",
    }

    resp = requests.get(ASOS_DAILY_URL, params=params, timeout=20)
    print("[ASOS] HTTP 상태 코드:", resp.status_code)

    if resp.status_code != 200:
        # 실제 시연용: 실패 이유 출력하고 예외 던져서 상위에서 가짜 데이터로 전환
        print("[ASOS] 응답 내용:", resp.text[:300])
        resp.raise_for_status()

    js = resp.json()
    items = js["response"]["body"]["items"]["item"]
    df = pd.DataFrame(items)

    # 사용할 후보 컬럼: 날짜, 평균습도, 일사/일조
    base_cols = ["tm", "avgRhm"]
    for c in base_cols:
        if c not in df.columns:
            raise RuntimeError(f"[ASOS] 응답에 {c} 컬럼이 없습니다. 실제 응답 구조를 확인하세요.")

    # 일사량 컬럼 우선순위
    rad_col = None
    if "sumGsr" in df.columns:
        rad_col = "sumGsr"
    elif "sumSsHr" in df.columns:
        rad_col = "sumSsHr"

    use_cols = base_cols + ([rad_col] if rad_col else [])
    df = df[use_cols].copy()

    df.rename(columns={"tm": "date", "avgRhm": "ext_humidity"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ext_humidity"] = pd.to_numeric(df["ext_humidity"], errors="coerce")

    if rad_col:
        df["ext_solar"] = pd.to_numeric(df[rad_col], errors="coerce")
    else:
        df["ext_solar"] = np.nan

    print("[ASOS] 일수:", len(df))
    return df


# ============= 1-1. API 실패 시 사용할 가짜 외부 데이터 생성 =============
def make_fake_asos_from_growth(df_growth, hum_col):
    """
    ASOS API 실패 시, 내부 데이터 기간에 맞춰
    '그럴듯한' 외부 습도/일사 데이터를 만드는 함수 (시연용).
    """
    print("[FAKE ASOS] 실제 API 실패 → 시연용 가짜 외부 데이터 생성합니다.")

    dates = sorted(df_growth["date"].unique())
    np.random.seed(42)  # 시연 때마다 같은 값 나오도록 고정

    fake_rows = []
    for d in dates:
        inside_mean_h = df_growth.loc[df_growth["date"] == d, hum_col].mean()

        # 외부 습도: 내부보다 대체로 약간 낮거나 비슷하게 (30~95% 사이 클리핑)
        ext_h = inside_mean_h - np.random.uniform(-5, 15)
        ext_h = float(np.clip(ext_h, 30, 95))

        # 외부 일사: 대충 맑은날/흐린날 섞인 느낌 (0~12 사이)
        ext_solar = float(np.random.choice([0, 2, 4, 6, 8, 10, 12], p=[0.1,0.1,0.15,0.2,0.2,0.15,0.1]))

        fake_rows.append({
            "date": d,
            "ext_humidity": ext_h,
            "ext_solar": ext_solar,
        })

    fake_df = pd.DataFrame(fake_rows)
    print("[FAKE ASOS] 생성된 일수:", len(fake_df))
    return fake_df


# ================== 2. 생육데이터 + VPD ==================
def load_growth_and_calc_vpd(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]

    # 시간 컬럼
    time_candidates = ["date_time", "일시", "수집일", "관측일시", "time", "datetime"]
    time_col = next((c for c in time_candidates if c in df.columns), None)
    if time_col is None:
        raise RuntimeError(f"[GROWTH] 시간 컬럼을 찾을 수 없습니다. 현재 컬럼: {list(df.columns)}")

    df[time_col] = pd.to_datetime(df[time_col])
    df["date"] = df[time_col].dt.date

    # 내부 온도/습도 컬럼
    temp_candidates = ["내부-내부온도", "내부온도", "temperature", "내부 온도"]
    hum_candidates  = ["내부-내부습도", "내부습도", "humidity", "내부 습도"]

    temp_col = next((c for c in temp_candidates if c in df.columns), None)
    hum_col  = next((c for c in hum_candidates if c in df.columns), None)

    if temp_col is None or hum_col is None:
        raise RuntimeError(
            f"[GROWTH] 내부 온도/습도 컬럼 없음\n"
            f"온도 후보: {temp_candidates}\n습도 후보: {hum_candidates}\n"
            f"현재 컬럼: {list(df.columns)}"
        )

    # VPD 계산
    def calc_vpd_kpa(temp_c, rh):
        es = 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))
        ea = es * (rh / 100.0)
        return es - ea

    df["vpd_kpa"] = calc_vpd_kpa(df[temp_col], df[hum_col])

    # 주간 여부
    rad_candidates = ["내부-내부일사량", "내부-일사", "일사량", "solar", "radiation"]
    rad_col = next((c for c in rad_candidates if c in df.columns), None)

    if rad_col is not None:
        df["is_daytime"] = df[rad_col] > 0
    else:
        df["is_daytime"] = df[time_col].dt.hour.between(6, 18)

    return df, time_col, temp_col, hum_col


# ================== 3. 메시지 생성 파이프라인 ==================
def run_vpd_control():
    # 1) 내부 데이터
    df, time_col, temp_col, hum_col = load_growth_and_calc_vpd(GROWTH_CSV_PATH)

    # 2) ASOS 외부 평균습도 + 일사 (실패 시 가짜데이터 사용)
    start_date = df["date"].min().strftime("%Y-%m-%d")
    end_date   = df["date"].max().strftime("%Y-%m-%d")

    try:
        df_asos = fetch_asos_daily_with_rh_rad(
            stn_id=STN_ID,
            start_date=start_date,
            end_date=end_date,
            service_key=SERVICE_KEY,
        )
        print("[INFO] 실제 ASOS 데이터를 사용합니다.")
    except Exception as e:
        print("[WARN] ASOS API 호출 실패:", e)
        df_asos = make_fake_asos_from_growth(df, hum_col)
        print("[INFO] 시연용 가짜 ASOS 데이터를 사용합니다.")

    # 3) 날짜 기준 merge
    merged = pd.merge(df, df_asos, on="date", how="left")

    # 4) 제어 메시지 로직
    def control_msg(row):
        if not row["is_daytime"]:
            return ""

        vpd = row["vpd_kpa"]
        in_h = row[hum_col]                         # 내부 습도
        ext_h = row.get("ext_humidity", np.nan)     # 외부 평균 상대습도
        ext_solar = row.get("ext_solar", np.nan)    # 외부 일사 (일사량 or 일조시간 합계)

        # ① VPD 낮음 → 보광 (+ 외부가 더 건조하면 환기도 같이 추천)
        if vpd < VPD_MIN:
            if not np.isnan(ext_h) and ext_h < in_h:
                return "보광이 필요합니다! / 환기를 추천드립니다!"
            return "보광이 필요합니다!"

        # ② VPD 높음 → 일사량 기준으로 차광 vs 환풍기
        if vpd > VPD_MAX:
            if np.isnan(ext_solar):
                return "환풍기를 돌리세요!"
            if ext_solar >= 5:
                return "차광을 하세요"
            else:
                return "환풍기를 돌리세요!"

        # ③ 그 외: 목표 범위(0.66~0.95) 근처 → 액션 없음
        return ""

    merged["control_message"] = merged.apply(control_msg, axis=1)
    msg_df = merged[merged["control_message"] != ""]
    return msg_df, time_col, hum_col, merged


# ================== 4. 출력 ==================
if __name__ == "__main__":
    msg_df, time_col, hum_col, merged = run_vpd_control()


    total_count = len(msg_df)
    print(f"\n=== 솔루션 총 개수: {total_count}개 ===")

    if msg_df.empty:
        print("메시지가 나온 row가 없습니다.")
    else:
        print("=== 솔루션 발생 시점 (상위 50개) ===")
        print(
            msg_df[[time_col, hum_col, "vpd_kpa", "ext_humidity", "ext_solar", "control_message"]]
            .head()    #요기!
            .to_string(index=False)
        )

        # 가장 최신 솔루션 1개
        latest = msg_df.sort_values(time_col).iloc[-1]
        print("\n=== 가장 최신 솔루션 1개 ===")
        print(
            f"시간: {latest[time_col]} | "
            f"내부습도: {latest[hum_col]:.1f}% | "
            f"외부습도: {latest['ext_humidity'] if not np.isnan(latest['ext_humidity']) else 'NaN'} | "
            f"외부일사: {latest['ext_solar'] if not np.isnan(latest['ext_solar']) else 'NaN'} | "
            f"VPD: {latest['vpd_kpa']:.3f} kPa | "
            f"추천: {latest['control_message']}"
        )

if __name__ == "__main__":
    msg_df, time_col, hum_col, merged = run_vpd_control()

    # 분석 기간
    start_date = merged["date"].min()
    end_date = merged["date"].max()

    if msg_df.empty:
        print("=== VPD 기반 온실 제어 요약 리포트 ===")
        print(f"- 분석 기간 : {start_date} ~ {end_date}")
        print("- 지정한 조건(VPD, 주간)에 해당하는 제어 권장 상황이 발생하지 않았습니다.")
    else:
        # ✅ 1. 총 개수
        total = len(msg_df)

        # ✅ 2. 메시지 유형 정리
        type_map = {
            "보광이 필요합니다! / 환기를 추천드립니다!": "보광 + 환기",
            "보광이 필요합니다!": "보광",
            "차광을 하세요": "차광",
            "환풍기를 돌리세요!": "환풍기"
        }
        msg_df["action_type"] = msg_df["control_message"].map(type_map).fillna("기타")

        type_counts = msg_df["action_type"].value_counts()

        # ✅ 3. 날짜별 발생 횟수
        daily_counts = (
            msg_df.groupby("date")["control_message"]
            .count()
            .sort_values(ascending=False)
        )

        # ✅ 4. 가장 최신 제어 사례
        latest = msg_df.sort_values(time_col).iloc[-1]

        # ✅ 보기 좋은 리포트 출력
        print("=== VPD 기반 온실 제어 요약 리포트 ===")
        print(f"- 분석 기간            : {start_date} ~ {end_date}")
        print(f"- 총 제어 권장 횟수    : {total}회")

        print("\n[권장 액션 유형별 발생 빈도]")
        for t, c in type_counts.items():
            print(f"  · {t:<8}: {c}회")

        print("\n[날짜별 제어 메시지 발생 TOP 7]")
        print(daily_counts.head(7).to_string(header=False))

        print("\n[대표 제어 사례 (가장 최근)]")
        print(
            f"  · 시간       : {latest[time_col]}\n"
            f"  · 내부습도   : {latest[hum_col]:.1f}%\n"
            f"  · 외부습도   : {latest['ext_humidity'] if not np.isnan(latest['ext_humidity']) else 'NaN'}%\n"
            f"  · 외부일사   : {latest['ext_solar'] if not np.isnan(latest['ext_solar']) else 'NaN'}\n"
            f"  · VPD        : {latest['vpd_kpa']:.3f} kPa\n"
            f"  · 권장 액션  : {latest['control_message']}"
        )

        print("\n[상세 로그 상위 30건]")
        print(
            msg_df[[time_col, hum_col, "vpd_kpa", "ext_humidity", "ext_solar", "control_message"]]
            .head(30)
            .to_string(index=False)
        )