import pandas as pd

# 1. csv 읽기
STATION_DIR = "data/지점코드.csv"

def load_station_table(csv_path: str) -> pd.DataFrame:
    """
    지점코드.csv 를 읽어서 DataFrame으로 반환.
    '지역' 열이 없으면 빈 문자열로 채운 열을 하나 추가.
    (네가 이미 지역을 직접 넣어둔 상태라면 그냥 그 값을 사용)
    """
    df = pd.read_csv(csv_path)

    if "지역" not in df.columns:
        df["지역"] = ""

    # 문자열 양쪽 공백 제거(있으면)
    for col in ["지역", "지점명"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def choose_region(df: pd.DataFrame) -> str:
    """
    DataFrame에서 '지역' 목록을 보여주고 사용자에게 선택받는다.
    """
    regions = sorted(df["지역"].dropna().unique())
    if not regions:
        raise ValueError("CSV에 '지역' 값이 없습니다. '지역' 열을 확인해주세요.")

    print("\n=== 지역 선택 ===")
    for i, r in enumerate(regions, start=1):
        print(f"{i}. {r}")

    while True:
        try:
            idx = int(input("번호를 선택하세요: ").strip())
            if 1 <= idx <= len(regions):
                region = regions[idx - 1]
                return region
        except ValueError:
            pass
        print("잘못된 입력입니다. 다시 입력해 주세요.")


def choose_station(df_region: pd.DataFrame) -> tuple[str, int]:
    """
    선택된 지역 내의 지점명을 보여주고 선택받는다.
    """
    # 지점명 가나다순으로 정렬
    df_sorted = df_region.sort_values("지점명").reset_index(drop=True)

    print("\n=== 지점(관측소) 선택 ===")
    for i, row in df_sorted.iterrows():
        print(f"{i+1}. {row['지점명']} (지점코드: {row['지점']})")

    while True:
        try:
            idx = int(input("번호를 선택하세요: ").strip())
            if 1 <= idx <= len(df_sorted):
                row = df_sorted.iloc[idx - 1]
                stn_name = row["지점명"]
                stn_code = int(row["지점"])  # 숫자 코드
                return stn_name, stn_code
        except ValueError:
            pass
        print("잘못된 입력입니다. 다시 입력해 주세요.")


# 4. 메인 흐름
# -----------------------------
def main():
    csv_path = STATION_DIR   # 네가 가진 지점 코드 파일 이름

    # 1) CSV 로드
    df = load_station_table(csv_path)

    # 2) 지역 선택
    region = choose_region(df)
    df_region = df[df["지역"] == region]
    print(f"\n[선택된 지역] {region} (지점 수: {len(df_region)})")

    # 3) 지점(관측소) 선택
    stn_name, stn_code = choose_station(df_region)

    # 4) 최종 STN_ID 문자열 만들기
    STN_ID = str(stn_code)

    print("\n=== 최종 선택 결과 ===")
    print(f"지역: {region}")
    print(f"지점명: {stn_name}")
    print(f"지점코드: {stn_code}")
    print(f'STN_ID = "{STN_ID}"')

    # 나중에 API 쓸 때는 여기서 STN_ID를 반환하거나 전역 변수로 써도 됨
    return STN_ID


if __name__ == "__main__":
    main()
