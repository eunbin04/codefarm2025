import requests
import pandas as pd

# ===== 0. 설정 =====
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"  # 공공데이터포털 발급 일반키(디코딩된 값)
STN_ID = "146"                               # 지점번호 (전주-전주기상지청 번호)
START_DATE = "2025-10-03"                    # 테스트용 시작일
END_DATE = "2025-11-02"                      # 테스트용 종료일

# 생육데이터 파일 & 컬럼명은 네 실제 CSV에 맞게 바꿔줘
GROWTH_CSV_PATH = "data/solution_dt.csv"          # 생육데이터 CSV 경로
DATETIME_COL = "date_time"                   # 생육데이터에서 시간 컬럼명
TEMP_COL = "temperature"                            # 생육데이터에서 기온 컬럼명
TEMP_DIFF_THRESHOLD = 10.0                    # 10도 이상 차이 나면 이상치로 보기


# ===== 1. 기상청 API 호출 함수 =====
def fetch_asos_daily(stn_id, start_date, end_date, service_key):
    """
    기상청 ASOS 일자료 OpenAPI에서
    [date, temp_api(avgTa), sunshine(sumSsHr)]만 가져오는 함수
    """

    # 1) 날짜 형식 변환
    start_dt = start_date.replace("-", "")
    end_dt = end_date.replace("-", "")

    # 2) URL
    url = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"

    # 3) 파라미터
    params = {
        "serviceKey": service_key,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "DAY",
        "startDt": start_dt,
        "endDt": end_dt,
        "stnIds": stn_id,
        "pageNo": "1",
        "numOfRows": "999"
    }

    # 4) 호출
    resp = requests.get(url, params=params)
    print("HTTP 상태 코드:", resp.status_code)
    resp.raise_for_status()

    js = resp.json()
    items = js["response"]["body"]["items"]["item"]

    # 5) DataFrame 변환
    df = pd.DataFrame(items)

    # 6) 필요한 컬럼만
    df = df[["tm", "avgTa", "sumSsHr"]].copy()
    df.rename(columns={
        "tm": "date",
        "avgTa": "temp_api",
        "sumSsHr": "sunshine"
    }, inplace=True)

    # 7) 타입 정리
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["temp_api"] = pd.to_numeric(df["temp_api"], errors="coerce")
    df["sunshine"] = pd.to_numeric(df["sunshine"], errors="coerce")

    return df


def api_test_call():
    """
    API 연결이 잘 되는지 테스트만 해보고 싶을 때 사용하는 함수
    """
    df_weather = fetch_asos_daily(
        stn_id=STN_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        service_key=SERVICE_KEY
    )

    print("=== [API 테스트] 기상청 ASOS 일자료 ===")
    print(df_weather.head())
    print("행 개수:", len(df_weather))


# ===== 2. 생육데이터 → 일별 평균 기온으로 정리 =====
def prepare_growth_daily(df_growth, datetime_col="date_time", temp_col="temp"):
    """
    시단위 생육 데이터를 날짜별 평균 기온만 남기도록 정리
    -> [date, temp_my]
    """
    df = df_growth.copy()
    df[datetime_col] = pd.to_datetime(df[datetime_col])
    df["date"] = df[datetime_col].dt.date

    df_daily = (
        df.groupby("date", as_index=False)[temp_col]
          .mean()
          .rename(columns={temp_col: "temp_my"})
    )

    return df_daily


# ===== 3. 기상청 기온 vs 생육 기온 비교 =====
def compare_temp(df_weather, df_growth_daily, diff_threshold=3.0):
    """
    날짜 기준으로 두 데이터를 merge하고
    기온 차이(temp_diff)가 큰 날만 골라냄
    """

    # 1) 날짜 기준으로 inner join
    df_merged = pd.merge(df_weather, df_growth_daily, on="date", how="inner")

    # 2) 기온 차이
    df_merged["temp_diff"] = (df_merged["temp_api"] - df_merged["temp_my"]).abs()

    # 3) 기준 이상만 필터
    df_outliers = df_merged[df_merged["temp_diff"] >= diff_threshold].copy()

    return df_merged, df_outliers


# ===== 4. 전체 파이프라인 실행 =====
def run_full_pipeline():
    # 1) 기상청 데이터 가져오기
    df_weather = fetch_asos_daily(
        stn_id=STN_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        service_key=SERVICE_KEY
    )
    print("\n[1] 기상청 데이터 (앞부분):")
    print(df_weather.head())

    # 2) 생육데이터 CSV 읽어서 일별 평균 만들기
    df_growth_raw = pd.read_csv(GROWTH_CSV_PATH)
    df_growth_daily = prepare_growth_daily(
        df_growth_raw,
        datetime_col=DATETIME_COL,
        temp_col=TEMP_COL
    )
    print("\n[2] 생육데이터 일별 평균 (앞부분):")
    print(df_growth_daily.head())

    # 3) 기온 비교 + 이상치 찾기
    df_all, df_outliers = compare_temp(
        df_weather,
        df_growth_daily,
        diff_threshold=TEMP_DIFF_THRESHOLD
    )

    print("\n[3] 기상청 vs 생육데이터 매칭 결과 (앞부분):")
    print(df_all.head())

    print(f"\n[4] 기온 차이가 {TEMP_DIFF_THRESHOLD}℃ 이상인 날들:")
    if df_outliers.empty:
        print("➡ 기준 이상으로 차이 나는 날이 없습니다.")
    else:
        print(df_outliers[["date", "sunshine", "temp_api", "temp_my", "temp_diff"]])

    # 4) CSV 저장 (선택)
    df_all.to_csv("asos_growth_compare_all.csv", index=False)
    df_outliers.to_csv("asos_growth_outliers.csv", index=False)
    print("\n[5] 결과 저장 완료: asos_growth_compare_all.csv, asos_growth_outliers.csv")


if __name__ == "__main__":
    # 🔹 1단계: API 연결만 먼저 테스트해보고 싶으면 이 줄만 실행되게 두고
    api_test_call()

    # 🔹 2단계: 생육데이터까지 비교 돌리고 싶으면 아래 주석을 풀면 됨
    run_full_pipeline()
