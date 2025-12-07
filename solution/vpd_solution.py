import pandas as pd

# 1. csv 읽기
STATION_DIR = "data/station_code.csv"

def load_station_table(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    if "지역" not in df.columns:
        df["지역"] = ""

    for col in ["지역", "지점명"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def choose_region(df: pd.DataFrame) -> str:
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


def choose_station(df_region: pd.DataFrame):
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


def select_station_interactive() -> str:
    """
    CSV에서 지역/지점을 선택해서 최종 STN_ID 문자열을 리턴하는 함수
    """
    csv_path = STATION_DIR

    df = load_station_table(csv_path)

    region = choose_region(df)
    df_region = df[df["지역"] == region]
    print(f"\n[선택된 지역] {region} (지점 수: {len(df_region)})")

    stn_name, stn_code = choose_station(df_region)

    STN_ID = str(stn_code)

    print("\n=== 최종 선택 결과 ===")
    print(f"지역: {region}")
    print(f"지점명: {stn_name}")
    print(f"지점코드: {stn_code}")
    print(f'STN_ID = "{STN_ID}"')

    return STN_ID

import requests
import pandas as pd

# ====================== 설정 ======================
SERVICE_KEY = "2403d03559e40daeeab89694df60abdabbf06848fe92122ee964798ceb14b6a9"  # data.go.kr Decoding 키
GROWTH_CSV_PATH = "mc_3m.csv"

ASOS_URL = "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"


# ================== 1. 온실 10분 평균 만들기 ==================

# lux -> W/m2 환산 상수 (대략적인 태양광 기준)
LUX_TO_WM2 = 0.0083  # 필요하면 0.01 정도로 조정해서 써도 됨

def make_greenhouse_10min(csv_path: str) -> pd.DataFrame:
    """
    온실 미기후 CSV에서 date_time 기준으로
    temperature, humidity, vpd 를 10분 평균으로 만드는 함수
    """
    df = pd.read_csv(csv_path, low_memory=False)

    # date_time 컬럼을 datetime 으로 변환 (예: "2025-09-01 T 00:01")
    df["datetime"] = pd.to_datetime(
        df["date_time"].str.replace(" T ", " "),
        errors="coerce"
    )

    # 인덱스로 설정 후 10분 평균
    df = df.set_index("datetime")
    cols_to_avg = ["temperature", "humidity", "vpd","light"]

    df_10min = df[cols_to_avg].resample("10min").mean().reset_index()

    df_10min["light_lux"] = df_10min["light"]
    df_10min["light_Wm2"] = df_10min["light"] * LUX_TO_WM2


    return df_10min


# ================== 2. 기상청 ASOS 시간자료 호출 ==================
def fetch_asos_hourly(stn_id: str,
                      start_dt: pd.Timestamp,
                      end_dt: pd.Timestamp,
                      service_key: str) -> pd.DataFrame:
    """
    기상청 AsosHourlyInfoService/getWthrDataList 에서
    start_dt ~ end_dt 기간의 시간자료(기온 ta, 습도 hm, 일사 icsr)를 JSON으로 받아 DataFrame으로 변환
    - stn_id: 지점번호 문자열 (예: "146")
    - API는 한번에 최대 1,000건을 넘을 수 없음. 날짜 범위가 넓으면 여러 번 호출해야 함.
    """
    all_items = []
    current_start_dt = start_dt

    while current_start_dt <= end_dt:
        # API는 YYYYMMDD, HH 형식을 사용
        start_date_str = current_start_dt.strftime("%Y%m%d")
        # 1000건 제한 때문에 하루씩 요청하는 것이 가장 확실한 방법. (최대 24시간 * 1일)
        # 하지만 데이터 없는 시간을 포함하면 1000건을 넘지 않을 수 있으므로, 일단은 전체를 요청하고
        # 실패하면 하루씩 요청하도록 변경
        current_end_dt = min(current_start_dt + pd.Timedelta(days=30), end_dt) # 일단 한달 단위로 잘라보기
        end_date_str = current_end_dt.strftime("%Y%m%d")

        params = {
            "serviceKey": service_key,
            "dataType": "JSON",   # JSON 으로 받자(XML도 가능하지만 파싱 귀찮음)
            "dataCd": "ASOS",     # 자료코드 (ASOS)
            "dateCd": "HR",       # 날짜코드 (HR: 시간자료)
            "startDt": start_date_str,
            "startHh": "00",
            "endDt": end_date_str,
            "endHh": "23",
            "stnIds": stn_id,     # 지점 번호
            "pageNo": "1",
            "numOfRows": "999",  # 1000건 제한을 피하기 위해 999로 설정
        }

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        resp = requests.get(ASOS_URL, params=params, headers=headers)
        print(f"[ASOS] Request for {start_date_str} to {end_date_str} status: {resp.status_code}")
        print("[ASOS] URL:", resp.url)

        if resp.status_code != 200:
            print("[ASOS] 에러 응답:")
            print(resp.text[:500])
            # API 응답이 1000건을 넘을 수 없다는 에러일 경우, 일 단위로 다시 요청
            if resp.json().get('response', {}).get('header', {}).get('resultCode') == '99':
                print("[ASOS] 데이터 요청 건수 초과. 일 단위로 재요청합니다.")
                day_start = current_start_dt
                while day_start <= current_end_dt:
                    day_end = day_start
                    day_start_str = day_start.strftime("%Y%m%d")
                    day_end_str = day_end.strftime("%Y%m%d")

                    day_params = params.copy()
                    day_params['startDt'] = day_start_str
                    day_params['endDt'] = day_end_str
                    day_params['numOfRows'] = '24' # 하루는 최대 24시간

                    day_resp = requests.get(ASOS_URL, params=day_params, headers=headers)
                    print(f"[ASOS] Daily request for {day_start_str} status: {day_resp.status_code}")
                    if day_resp.status_code == 200:
                        day_data = day_resp.json()
                        try:
                            day_items = day_data["response"]["body"]["items"]["item"]
                            if day_items:
                                all_items.extend(day_items)
                        except KeyError:
                            print(f"[ASOS] Daily request for {day_start_str}: items 없음 / 구조 이상")
                            print(day_data)
                    else:
                        print(f"[ASOS] Daily request for {day_start_str} 에러 응답:")
                        print(day_resp.text[:500])
                    day_start += pd.Timedelta(days=1)
                current_start_dt = current_end_dt + pd.Timedelta(days=1) # 다음 기간으로 이동
                continue # 다음 월 단위 요청으로 넘어감
            else:
                current_start_dt += pd.Timedelta(days=1) # Prevent infinite loop if other error
                continue # 다른 에러라면 일단 다음 기간으로 넘어감

        data = resp.json()
        try:
            items = data["response"]["body"]["items"]["item"]
            if items:
                all_items.extend(items)
        except KeyError:
            print("[ASOS] items 없음 / 구조 이상:")
            print(data)

        current_start_dt = current_end_dt + pd.Timedelta(days=1)

    if not all_items:
        print("[ASOS] 데이터 없음")
        return pd.DataFrame()

    # tm(시간), ta(기온), hm(습도), icsr(일사, MJ/m2) 사용
    rows = []
    for it in all_items:
        rows.append({
            "datetime": it.get("tm"),     # "2019-01-20 01:00"
            "ext_temp": it.get("ta"),     # 기온(°C)
            "ext_rh": it.get("hm"),       # 습도(%)
            "ext_icsr_MJ": it.get("icsr") # 일사(MJ/m2)
        })

    df_hourly = pd.DataFrame(rows)

    # 타입 변환
    df_hourly["datetime"] = pd.to_datetime(df_hourly["datetime"],
                                           format="%Y-%m-%d %H:%M",
                                           errors="coerce")
    df_hourly["ext_temp"] = pd.to_numeric(df_hourly["ext_temp"], errors="coerce")
    df_hourly["ext_rh"] = pd.to_numeric(df_hourly["ext_rh"], errors="coerce")
    df_hourly["ext_icsr_MJ"] = pd.to_numeric(df_hourly["ext_icsr_MJ"], errors="coerce").fillna(0)

    # 일사(MJ/m2)를 평균 복사에너지 (W/m2)로 변환
    # 1시간 누적 MJ/m2 → W/m2 : MJ * 1e6 / 3600
    df_hourly["ext_icsr_Wm2"] = df_hourly["ext_icsr_MJ"] * (1_000_000 / 3600.0)

    return df_hourly


# ================== 3. ASOS 시간자료 → 10분 단위로 보간 ==================
def make_asos_10min(df_hourly: pd.DataFrame,
                    start_dt: pd.Timestamp,
                    end_dt: pd.Timestamp) -> pd.DataFrame:
    """
    시간단위 ASOS 자료(df_hourly)를 10분 단위로 시간 보간해서 만드는 함수
    - start_dt ~ end_dt 범위로 10분 freq 인덱스를 생성 후 interpolate
    """
    if df_hourly.empty:
        print("[ASOS] 시간자료 DF가 비어있음")
        return df_hourly

    df_hourly = df_hourly.set_index("datetime").sort_index()

    # 10분 간격 타임라인 생성
    # 온실 데이터 범위와 맞추기 위해 start_dt ~ end_dt
    start_10 = start_dt.floor("10min")
    end_10   = end_dt.ceil("10min")

    idx_10min = pd.date_range(start_10, end_10, freq="10min")

    # 시간 보간 (온도, 습도, 일사)
    df_10min_ext = df_hourly.reindex(idx_10min).interpolate(method="time")

    df_10min_ext = df_10min_ext.reset_index().rename(columns={"index": "datetime"})

    return df_10min_ext

# ================== 4. 온실 10분 평균 + 외부(ASOS) 10분 자료 병합 ==================

def merge_greenhouse_with_asos(stn_id: str):
    # 4-1) 온실 10분 평균
    df_gh_10 = make_greenhouse_10min(GROWTH_CSV_PATH)
    print("[GH] 온실 10분 평균 행 수:", len(df_gh_10))

    start_dt = df_gh_10["datetime"].min()
    end_dt   = df_gh_10["datetime"].max()
    print("[기간] 온실 데이터:", start_dt, "~", end_dt)

    # 4-2) ASOS 시간자료
    df_asos_hour = fetch_asos_hourly(stn_id, start_dt, end_dt, SERVICE_KEY)
    print("[ASOS] 시간자료 행 수:", len(df_asos_hour))

    if df_asos_hour.empty:
        print("[WARN] ASOS 시간자료가 비어있어서 외기 데이터 없이 온실 데이터만 반환합니다.")
        return df_gh_10

    df_asos_10 = make_asos_10min(df_asos_hour, start_dt, end_dt)
    print("[ASOS] 10분 보간 행 수:", len(df_asos_10))

    df_merged = pd.merge(
        df_gh_10,
        df_asos_10,
        how="left",
        on="datetime"
    )

    print("[최종 병합 미리보기]")
    print(
      df_merged[[
          "datetime",
          "temperature", "humidity", "vpd",
          "light_lux", "light_Wm2",
          "ext_temp", "ext_rh", "ext_icsr_MJ", "ext_icsr_Wm2"
      ]].head().to_string(index=False)
      )


     # CSV로 저장 (전체 데이터)
    output_path = "/content/drive/MyDrive/final_project/merged_all_10min.csv"
    df_merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[INFO] 병합 데이터 CSV 저장 완료: {output_path}")

    return df_merged

    # 🔥 여기서부터 VPD 4.5 이상만 출력
    # ==========================
    # vpd_threshold = 4.0

    # cols_to_show = [
    #     "datetime",
    #     "temperature", "humidity", "vpd",
    #     "ext_temp", "ext_rh", "ext_icsr_MJ", "ext_icsr_Wm2"
    # ]

    # # vpd가 4.5 이상인 행만 필터링
    # df_high_vpd = df_merged[df_merged["vpd"] >= vpd_threshold]

    # print(f"\n[VPD ≥ {vpd_threshold} 인 행만 출력]")
    # if df_high_vpd.empty:
    #     print("조건을 만족하는 데이터가 없습니다.")
    # else:
    #     print(df_high_vpd[cols_to_show].to_string(index=False))


    # return df_merged


# (선택) 나중에 인터랙티브하게 고를 수 있도록 준비만 해둔 함수들
def select_material_interactive(materials_dict: dict, title: str, default_key: str = None) -> str:
    print(f"\n=== {title} 선택 ===")
    keys = list(materials_dict.keys())
    for i, key in enumerate(keys, start=1):
        print(f"{i}. {materials_dict[key]['name_kr']}")

    if default_key and default_key in keys:
        print(f"(기본값: {materials_dict[default_key]['name_kr']})")

    while True:
        try:
            user_input = input("번호를 선택하세요 (기본값 엔터): ").strip()
            if not user_input and default_key:
                return default_key

            idx = int(user_input)
            if 1 <= idx <= len(keys):
                return keys[idx - 1]
        except ValueError:
            pass
        print("잘못된 입력입니다. 다시 입력해 주세요.")

def select_cover_material_interactive(default_key: str = "glass_single") -> str:
    """
    COVER_MATERIALS에서 피복재를 사용자에게 선택받는 함수.
    아무것도 입력 안 하면 default_key 사용.
    """
    print("\n[피복재 선택]")
    keys = list(COVER_MATERIALS.keys())
    for i, k in enumerate(keys, start=1):
        info = COVER_MATERIALS[k]
        print(f"  {i}. {info['name_kr']} ({k}, 투과율 τ={info['tau']})")

    choice = input(f"번호를 선택하세요 (기본: 1, 기본키={default_key}): ").strip()

    if choice == "":
        # 그냥 엔터 → 기본값
        return default_key

    # 숫자 입력했을 때
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    except ValueError:
        pass

    print("[WARN] 잘못된 입력입니다. 기본값을 사용합니다.")
    return default_key

# ================== 6. 차광스크린 유무에 따른 온도 변화 계산 ==================

# 피복재(유리/필름) 별 투과율 (임의 값, 나중에 실제 값으로 교체해도 됨)
COVER_MATERIALS = {
    "glass_single": {  # 단층 유리
        "name_kr": "단층 유리",
        "tau": 0.70,   # 투과율 (placeholder)
    },
    "pe_single": {     # 단층 PE 필름
        "name_kr": "단층 PE필름",
        "tau": 0.65,   # placeholder
    },
    "pe_double": {     # 이중 PE 필름
        "name_kr": "이중 PE필름",
        "tau": 0.55,   # placeholder
    },
}

# 차광스크린 소재별 차광률 (임의 값, 나중에 실제 스펙으로 교체)
SCREEN_MATERIALS = {
    "none": {
        "name_kr": "차광 없음",
        "shading_rate": 0.0,   # 차광 X
    },
    "screen_35": {
        "name_kr": "차광스크린 35%",
        "shading_rate": 0.35,  # placeholder
    },
    "screen_50": {
        "name_kr": "차광스크린 50%",
        "shading_rate": 0.50,  # placeholder
    },
    "screen_70": {
        "name_kr": "차광스크린 70%",
        "shading_rate": 0.70,  # placeholder
    },
}


def estimate_inside_temp_with_shading(
    df_merged: pd.DataFrame,
    cover_type: str,
    screen_type: str,
    gh_floor_area: float,  # 온실 바닥 면적 [m2] (예: 10m x 40m)
    gh_height: float,        # 평균 높이 [m]
    U: float = 6.0,                # 피복 열관류율 [W/m2K] (전도+복사+대류 통합)
    ACH: float = 20.0,              # 자연환기 공기교환 횟수 [h-1]
) -> pd.DataFrame:
    """
    병합된 DF(df_merged)를 받아서
    - 외기 일사(ext_icsr_Wm2)와 기온(ext_temp)을 이용해
    - '무차광' / '차광스크린 사용' 시의 모델 내부온도를 계산하고
    - 각 시점별 온도 차이(ΔT)를 새로운 컬럼으로 추가하는 함수.

    ※ cover_type, screen_type 은 위의 COVER_MATERIALS / SCREEN_MATERIALS key 를 사용.
    ※ gh_floor_area, gh_height, U, ACH 는 나중에 실제 온실 파라미터로 수정하면 됨.
    """

    df = df_merged.copy()

    # ---------- 1) 피복 투과율 / 스크린 차광률 가져오기 ----------
    if cover_type not in COVER_MATERIALS:
        raise ValueError(f"알 수 없는 cover_type: {cover_type} (COVER_MATERIALS에 key 추가 필요)")

    if screen_type not in SCREEN_MATERIALS:
        raise ValueError(f"알 수 없는 screen_type: {screen_type} (SCREEN_MATERIALS에 key 추가 필요)")

    tau_cover = COVER_MATERIALS[cover_type]["tau"]                 # 피복 투과율
    S_screen = SCREEN_MATERIALS[screen_type]["shading_rate"]       # 차광률 (0~1)

    # ---------- 2) 온실 기하/열손실 계수 계산 ----------
    gh_volume = gh_floor_area * gh_height                          # 온실 부피 [m3]

    # 외피 면적 (벽+지붕). 여기선 바닥 면적의 1.6배로 대략 가정 (임의값, 필요 시 수정)
    gh_envelope_area = gh_floor_area * 1.6                         # [m2]

    rho_air = 1.2          # 공기 밀도 [kg/m3]
    cp_air = 1000.0        # 공기 비열 [J/kgK]

    # 피복을 통한 열손실 계수 [W/K]
    G_env = U * gh_envelope_area

    # 환기(자연환기)에 의한 열손실 계수 [W/K]
    # G_vent = rho * cp * (V * ACH / 3600)
    G_vent = rho_air * cp_air * (gh_volume * ACH / 3600.0)

    # 총 열손실 계수
    G_loss = G_env + G_vent

    # ---------- 3) 시점별 일사열 / 내부온도 계산 ----------
    # 외부 일사 [W/m2] (ASOS에서 변환해 둔 컬럼, 없으면 0으로)
    G_ext = df.get("ext_icsr_Wm2", pd.Series(0.0, index=df.index)).fillna(0.0)

    # 외기온도 [°C]
    T_out = df.get("ext_temp", pd.Series(pd.NA, index=df.index))

    # 단파 일사에 의한 열유입 (무차광 / 차광)
    # Q = G_ext [W/m2] * 바닥면적 [m2] * 투과율
    Q_solar_noshade = G_ext * gh_floor_area * tau_cover
    Q_solar_shaded = G_ext * gh_floor_area * tau_cover * (1.0 - S_screen)

    # 모델 내부온도 (°C)
    # T_in = T_out + Q_solar / G_loss
    df["T_in_model_noshade"] = T_out + (Q_solar_noshade / G_loss)
    df["T_in_model_shaded"] = T_out + (Q_solar_shaded / G_loss)

    # 차광스크린으로 인한 온도 하락량 ΔT (무차광 - 차광)
    df["deltaT_screen"] = df["T_in_model_noshade"] - df["T_in_model_shaded"]

    # 참고용: 실제 온실 온도와 모델값 비교 (원하면 주간만 골라서 보거나 해도 됨)
    if "temperature" in df.columns:
        df["T_measured"] = df["temperature"]
        df["error_measured_vs_model_shaded"] = df["T_measured"] - df["T_in_model_shaded"]

    return df


# (선택) 나중에 인터랙티브하게 고를 수 있도록 준비만 해둔 함수들
# 지금은 안 써도 되지만, 나중에 input()으로 선택하게 만들고 싶을 때 활용 가능

def add_vpd_for_shading(df_with_shading: pd.DataFrame) -> pd.DataFrame:
    """
    df_with_shading 안에 다음 컬럼이 있다고 가정:
      - temperature : 실제 온실 온도 [°C]
      - humidity    : 실제 온실 상대습도 [%]
      - T_in_model_shaded : 차광 모델로 추정한 내부 온도 [°C]

    이 함수가 추가로 만드는 컬럼:
      - vpd_measured         : 실제 측정 온도/습도로 다시 계산한 VPD [kPa]
      - RH_model_shaded      : '절대습도 일정' 가정 하에서 차광 후 RH [%]
      - vpd_model_shaded     : T_in_model_shaded + RH_model_shaded 로 계산한 VPD
      - deltaVPD_shading     : vpd_measured - vpd_model_shaded (차광으로 VPD 얼마나 줄었는지)
    """

    df = df_with_shading.copy()

    # 체크
    for col in ["temperature", "humidity", "T_in_model_shaded"]:
        if col not in df.columns:
            raise KeyError(f"'{col}' 컬럼이 df_with_shading 안에 없습니다. 먼저 해당 컬럼이 생성되도록 코드를 확인하세요.")

    # 1) 기준: 실제 측정값 기반 VPD
    T_meas = df["temperature"]
    RH_meas = df["humidity"]

    df["vpd_measured"] = calc_vpd_kPa(T_meas, RH_meas)

    # 2) 차광 후: 온도는 T_in_model_shaded 로, 절대습도는 그대로라고 가정
    T_shaded = df["T_in_model_shaded"]

    df["RH_model_shaded"] = recalc_rh_const_abs_humidity(
        T_old_C=T_meas,
        RH_old=RH_meas,
        T_new_C=T_shaded
    )

    df["vpd_model_shaded"] = calc_vpd_kPa(
        T_C=T_shaded,
        RH=df["RH_model_shaded"]
    )

    # 3) 차광으로 인한 VPD 감소량 (양수이면 '그만큼 줄어든 것'으로 볼 수 있음)
    df["deltaVPD_shading"] = df["vpd_measured"] - df["vpd_model_shaded"]

    return df

if __name__ == "__main__":
    STN_ID = select_station_interactive()
    df_final = merge_greenhouse_with_asos(STN_ID)

    if df_final is not None and not df_final.empty:
        # ================== 사용자에게 파라미터 입력 받기 ==================
        cover_type = select_cover_material_interactive()
        screen_type = select_screen_material_interactive(default_key="screen_50")

        gh_floor_area = ask_float("온실 바닥 면적 [m2]", 400.0)
        gh_height     = ask_float("온실 평균 높이 [m]", 4.0)
        U             = ask_float("피복 열관류율 U [W/m2K]", 6.0)
        ACH           = ask_float("자연환기 ACH [h-1]", 20.0)

        # ================== 선택값으로 모델 온도 계산 ==================
        df_with_shading = estimate_inside_temp_with_shading(
            df_final,
            cover_type=cover_type,
            screen_type=screen_type,
            gh_floor_area=gh_floor_area,
            gh_height=gh_height,
            U=U,
            ACH=ACH
        )

        print("\n[차광스크린 적용 전/후 모델 온도 미리보기]")
        print(
            df_with_shading[[
                "datetime",
                "ext_temp",
                "T_in_model_noshade",
                "T_in_model_shaded",
                "deltaT_screen"
            ]].head().to_string(index=False)
        )

        output_shading_path = "/content/drive/MyDrive/final_project/merged_with_shading_temp.csv"
        df_with_shading.to_csv(output_shading_path, index=False, encoding="utf-8-sig")
        print(f"[INFO] 차광스크린 효과 포함 데이터 CSV 저장 완료: {output_shading_path}")

        # (그 아래에 VPD 민감도 계산 붙어 있으면 그대로 유지)
        # df_with_vpd = add_vpd_sensitivity_using_dewpoint(df_with_shading)
        # ...

import numpy as np
import pandas as pd

def sat_vapor_pressure_kpa(T_c):
    """
    포화수증기압 es(T) [kPa]
    T_c : 섭씨온도(°C) (스칼라/Series 다 가능)
    """
    T = np.asarray(T_c, dtype="float64")
    return 0.6108 * np.exp((17.27 * T) / (T + 237.3))

def add_vpd_sensitivity_using_dewpoint(df_merged: pd.DataFrame) -> pd.DataFrame:
    """
    merge_greenhouse_with_asos() 혹은 estimate_inside_temp_with_shading() 결과 DF에 대해
    '이슬점(dew_point)을 기준으로' 온도 변화에 따른 VPD 변화를 계산해 붙여준다.

    필요 정보:
      - temperature : 현재 온실 공기온도(°C)
      - humidity    : 현재 상대습도(%)
      - vpd         : (옵션) 기존 시스템 VPD (검산용)
      - dew_point   : (옵션) 이미 있으면 그대로 사용, 없으면 T+RH로 계산
      - T_in_model_noshade  : (옵션) 차광 없다고 가정한 모델 온도(°C)
      - T_in_model_shaded   : (옵션) 차광 있을 때 모델 온도(°C)
    """
    df = df_merged.copy()

    # 0) dew_point 컬럼이 없으면 temperature + humidity 로 계산해서 만든다
    if "dew_point" not in df.columns:
        T = df["temperature"].astype("float64")
        RH = df["humidity"].astype("float64")

        # RH(%) → 0~1 비율
        rh_frac = RH / 100.0
        valid = T.notna() & rh_frac.notna() & (rh_frac > 0) & (rh_frac <= 1)

        # Magnus 공식으로 이슬점 계산
        # gamma = ln(RH) + (a*T)/(b+T)
        # T_dew = (b*gamma)/(a-gamma)
        a, b = 17.27, 237.3
        gamma = np.log(rh_frac[valid]) + (a * T[valid]) / (b + T[valid])
        T_dew = (b * gamma) / (a - gamma)

        df.loc[valid, "dew_point"] = T_dew

    # 필수 컬럼 존재 확인
    for c in ["temperature", "dew_point"]:
        if c not in df.columns:
            raise ValueError(f"필수 컬럼 '{c}' 이 없습니다.")

    # 실제 계산에 쓸 행 (온도, 이슬점 둘 다 있는 행)
    mask = df["temperature"].notna() & df["dew_point"].notna()
    T_air = df.loc[mask, "temperature"]
    T_dew = df.loc[mask, "dew_point"]

    # 1) 이슬점으로부터 실제 수증기압 ea 구하기 (ea = es(T_dew))
    ea = sat_vapor_pressure_kpa(T_dew)
    es_air = sat_vapor_pressure_kpa(T_air)
    vpd_from_dew = es_air - ea  # 이론적인 VPD

    df.loc[mask, "ea_kPa"]           = ea
    df.loc[mask, "es_air_kPa"]       = es_air
    df.loc[mask, "vpd_from_dew_kPa"] = vpd_from_dew
    df.loc[mask, "RH_from_dew_%"]    = (ea / es_air) * 100.0

    # 기존 vpd와 비교 (물리적으로 잘 맞는지 확인용)
    if "vpd" in df.columns:
        df.loc[mask, "vpd_diff_vs_sensor_kPa"] = df.loc[mask, "vpd"] - vpd_from_dew

    # 2) 온도 +1, +2, +3 °C 일 때 VPD 변화
    for dT in (1.0, 2.0, 3.0):
        T_new = T_air + dT
        es_new = sat_vapor_pressure_kpa(T_new)
        vpd_new = es_new - ea   # 공기 중 수증기양(ea)은 그대로라고 가정

        col_vpd = f"vpd_plus_{int(dT)}C_kPa"
        col_dlt = f"delta_vpd_plus_{int(dT)}C_kPa"

        df.loc[mask, col_vpd] = vpd_new
        df.loc[mask, col_dlt] = vpd_new - vpd_from_dew

    # 3) 차광 없음 모델 온도
    if "T_in_model_noshade" in df.columns:
        T_model_ns = df.loc[mask, "T_in_model_noshade"]
        es_model_ns = sat_vapor_pressure_kpa(T_model_ns)
        vpd_model_ns = es_model_ns - ea

        df.loc[mask, "vpd_T_in_model_noshade_kPa"] = vpd_model_ns
        df.loc[mask, "delta_vpd_T_in_model_noshade_kPa"] = (
            vpd_model_ns - vpd_from_dew
        )

    # 4) 차광 있을 때 모델 온도
    if "T_in_model_shaded" in df.columns:
        T_model_sh = df.loc[mask, "T_in_model_shaded"]
        es_model_sh = sat_vapor_pressure_kpa(T_model_sh)
        vpd_model_sh = es_model_sh - ea

        df.loc[mask, "vpd_T_in_model_shaded_kPa"] = vpd_model_sh
        df.loc[mask, "delta_vpd_T_in_model_shaded_kPa"] = (
            vpd_model_sh - vpd_from_dew
        )

    # 5) noshade vs shaded VPD 차이
    if "T_in_model_noshade" in df.columns and "T_in_model_shaded" in df.columns:
        df.loc[mask, "delta_vpd_noshade_minus_shaded_kPa"] = (
            df.loc[mask, "vpd_T_in_model_noshade_kPa"]
            - df.loc[mask, "vpd_T_in_model_shaded_kPa"]
        )

    # --- 요약값 프린트 (전체 평균) ---
    if "delta_vpd_plus_2C_kPa" in df.columns:
        mean_d2 = float(df.loc[mask, "delta_vpd_plus_2C_kPa"].mean())
        print(
            "[요약] 같은 공기(이슬점=수증기 양 동일)에서 온도 +2°C 하면 "
            f"VPD가 평균 {mean_d2:.3f} kPa 정도 증가합니다."
        )

    if "delta_vpd_T_in_model_shaded_kPa" in df.columns:
        mean_sh = float(df.loc[mask, "delta_vpd_T_in_model_shaded_kPa"].mean())
        print(
            "[요약] 현재 온도 대신 '차광 모델 온도(T_in_model_shaded)'를 쓰면 "
            f"VPD가 평균 {mean_sh:.3f} kPa 만큼 달라집니다."
        )

    if "delta_vpd_noshade_minus_shaded_kPa" in df.columns:
        mean_diff = float(df.loc[mask, "delta_vpd_noshade_minus_shaded_kPa"].mean())
        print(
            "[요약] 모델 기준으로 차광 스크린 ON (noshade → shaded)일 때 "
            f"VPD 차이 평균은 {mean_diff:.3f} kPa 입니다. "
            "(양수면 스크린이 VPD를 줄인다는 뜻)"
        )

    return df

# 환기에 따라서 변하는 온도랑 습도
import numpy as np
import pandas as pd

def sat_vapor_pressure_kpa(T_c):
    """
    포화수증기압 es(T) [kPa]
    T_c : 섭씨온도(°C)
    """
    T = np.asarray(T_c, dtype="float64")
    return 0.6108 * np.exp((17.27 * T) / (T + 237.3))


def add_ea_in_out_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    DF에 내부/외부 수증기압 컬럼(ea_in_obs_kPa, ea_out_kPa)을 추가한다.
    - 내부: dew_point 있으면 그걸로, 없으면 temperature + humidity로 계산
    - 외부: ext_temp + ext_rh 사용
    """
    df = df.copy()

    # --- 내부 수증기압 ---
    if "dew_point" in df.columns:
        mask_dp = df["dew_point"].notna()
        df.loc[mask_dp, "ea_in_obs_kPa"] = sat_vapor_pressure_kpa(df.loc[mask_dp, "dew_point"])
    elif "temperature" in df.columns and "humidity" in df.columns:
        mask_trh = df["temperature"].notna() & df["humidity"].notna()
        es_in = sat_vapor_pressure_kpa(df.loc[mask_trh, "temperature"])
        rh_frac = df.loc[mask_trh, "humidity"] / 100.0
        df.loc[mask_trh, "ea_in_obs_kPa"] = es_in * rh_frac
    else:
        raise ValueError("내부 수증기압을 계산하려면 dew_point 또는 (temperature + humidity)가 필요합니다.")

    # --- 외부 수증기압 ---
    if "ext_temp" in df.columns and "ext_rh" in df.columns:
        mask_ext = df["ext_temp"].notna() & df["ext_rh"].notna()
        es_out = sat_vapor_pressure_kpa(df.loc[mask_ext, "ext_temp"])
        rh_out = df.loc[mask_ext, "ext_rh"] / 100.0
        df.loc[mask_ext, "ea_out_kPa"] = es_out * rh_out
    else:
        raise ValueError("외부 수증기압을 계산하려면 ext_temp + ext_rh가 필요합니다.")

    return df


def simulate_ventilation_effect_simple(
    df_input: pd.DataFrame,
    vent_angle_deg: float,
    vent_angle_max_deg: float = 45.0,
    temp_base_col: str = "T_in_model_shaded",
    prefix: str = "vent_",
) -> pd.DataFrame:
    """
    ACH를 전혀 쓰지 않고,
    '천창/측창 개폐각'만으로 환기 효과(열손실 + 습도/VPD 변화)를 시뮬레이션하는 함수.

    아이디어:
      - vent_frac = vent_angle_deg / vent_angle_max_deg   (0~1)
      - 온도:  T_after = (1 - vent_frac)*T_base + vent_frac*T_out
      - 수증기:ea_after = (1 - vent_frac)*ea_in_obs + vent_frac*ea_out
      - VPD_after = es(T_after) - ea_after

    temp_base_col:
      - "T_in_model_shaded"  : 차광 모델 온도 기준 (추천)
      - "T_in_model_noshade" : 무차광 모델 기준
      - "temperature"        : 그냥 실측 온도 기준
    """
    # 내부/외부 수증기압 먼저 계산
    df = add_ea_in_out_columns(df_input)
    df = df.copy()

    mask = (
        df["ea_in_obs_kPa"].notna()
        & df["ea_out_kPa"].notna()
        & df["ext_temp"].notna()
    )

    # 1) 각도 -> 환기 강도 (0~1)
    vent_frac = vent_angle_deg / vent_angle_max_deg
    vent_frac = max(0.0, min(1.0, vent_frac))  # 0~1로 고정

    df[prefix + "angle_deg"] = vent_angle_deg
    df[prefix + "frac"] = vent_frac

    # 2) 기준 온도 선택 (차광 모델 온도 우선)
    if temp_base_col in df.columns:
        T_base = df.loc[mask, temp_base_col]
    else:
        print(f"[WARN] '{temp_base_col}' 컬럼이 없어 'temperature'를 사용합니다.")
        T_base = df.loc[mask, "temperature"]

    T_out = df.loc[mask, "ext_temp"]

    # 3) 환기 후 온도 (열손실 반영: 외기 쪽으로 섞임)
    #    T_after = (1 - vent_frac)*T_base + vent_frac*T_out
    T_after = (1.0 - vent_frac) * T_base + vent_frac * T_out

    df.loc[mask, prefix + "T_before_C"] = T_base
    df.loc[mask, prefix + "T_after_C"]  = T_after
    df.loc[mask, prefix + "deltaT_C"]   = T_after - T_base  # 보통 음수 (냉각)

    # 열손실 비율 (외기 쪽으로 얼마나 가까워졌는지)
    # heat_loss_ratio = (T_base - T_after) / (T_base - T_out)
    # T_base == T_out 인 경우 0으로 처리
    delta_T_full = (T_base - T_out)
    with np.errstate(divide="ignore", invalid="ignore"):
        heat_loss_ratio = (T_base - T_after) / delta_T_full
    heat_loss_ratio = heat_loss_ratio.clip(lower=0.0, upper=1.0)
    df.loc[mask, prefix + "heat_loss_ratio"] = heat_loss_ratio

    # 4) 환기 후 수증기압 (실내/외 혼합)
    ea_in = df.loc[mask, "ea_in_obs_kPa"]
    ea_out = df.loc[mask, "ea_out_kPa"]

    ea_after = (1.0 - vent_frac) * ea_in + vent_frac * ea_out
    df.loc[mask, prefix + "ea_after_kPa"] = ea_after

    # 5) VPD, RH 계산
    es_after = sat_vapor_pressure_kpa(T_after)
    VPD_after = es_after - ea_after
    RH_after = (ea_after / es_after) * 100.0

    df.loc[mask, prefix + "VPD_kPa"] = VPD_after
    df.loc[mask, prefix + "RH_%"]    = RH_after

    # 6) 현재 VPD와 비교 (있으면)
    if "vpd" in df.columns:
        df.loc[mask, prefix + "deltaVPD_vs_sensor_kPa"] = (
            df.loc[mask, prefix + "VPD_kPa"] - df.loc[mask, "vpd"]
        )

    # === 요약 출력: 평균 온도 변화 + 평균 VPD 변화 ===
    mean_dT = float(df.loc[mask, prefix + "deltaT_C"].mean())
    mean_heat_loss = float(df.loc[mask, prefix + "heat_loss_ratio"].mean())
    print(
        f"[요약][각도={vent_angle_deg:.1f}°] "
        f"평균 온도 변화 {mean_dT:.2f} °C, "
        f"외기와의 온도 차 중 약 {mean_heat_loss*100:.1f}% 만큼 환기로 상쇄됨."
    )

    if prefix + "deltaVPD_vs_sensor_kPa" in df.columns:
        mean_dV = float(df.loc[mask, prefix + "deltaVPD_vs_sensor_kPa"].mean())
        print(
            f"        평균 VPD 변화(현재 VPD 대비) {mean_dV:.3f} kPa"
        )

    return df

# ================== 8. 이슬점 기반 VPD 민감도 계산 ==================
df_with_vpd = add_vpd_sensitivity_using_dewpoint(df_with_shading)

print("\n[VPD 민감도 계산 결과 (앞 5행)]")
print(
    df_with_vpd[[
        "datetime",
        "temperature",
        "humidity",
        "dew_point",
        "vpd",                # 기존 컨트롤러 VPD
        "vpd_from_dew_kPa",   # 이슬점 기반 재계산 VPD
        "vpd_plus_2C_kPa",    # 온도 +2°C 가정 VPD
        "delta_vpd_plus_2C_kPa",
        "vpd_T_in_model_noshade_kPa",
        "vpd_T_in_model_shaded_kPa",
        "delta_vpd_T_in_model_noshade_kPa",
        "delta_vpd_T_in_model_shaded_kPa",
        "delta_vpd_noshade_minus_shaded_kPa",
    ]].head().to_string(index=False)
)

# 전체를 파일로도 보고 싶으면 (싫으면 이 블록은 지워도 됨)
vpd_output_path = "/content/drive/MyDrive/final_project/merged_with_shading_temp_vpd_sensitivity.csv"
df_with_vpd.to_csv(vpd_output_path, index=False, encoding="utf-8-sig")
print(f"[INFO] VPD 민감도 포함 CSV 저장 완료: {vpd_output_path}")

# ================== 환기 각도에 따른 열손실 + 습도/VPD 변화 시뮬레이션 ==================
# 예: 창 각도 0°, 15°, 30°, 45° 에 대해 컬럼 추가

angles = [0.0, 15.0, 30.0, 45.0]

for ang in angles:
    prefix = f"vent_{int(ang)}deg_"
    df_with_shading = simulate_ventilation_effect_simple(
        df_with_shading,
        vent_angle_deg=ang,
        vent_angle_max_deg=45.0,           # 최대 개방각
        temp_base_col="T_in_model_shaded", # 차광 모델 온도 기준
        prefix=prefix,
    )

print("\n[환기 각도별 열손실 + VPD 변화 미리보기]")
cols_to_show = [
    "datetime",
    "temperature", "humidity", "vpd",
    "ext_temp",
    "T_in_model_shaded",
    "vent_0deg_T_after_C",
    "vent_0deg_VPD_kPa",
    "vent_30deg_T_after_C",
    "vent_30deg_VPD_kPa",
    "vent_45deg_T_after_C",
    "vent_45deg_VPD_kPa",
]
print(df_with_shading[cols_to_show].head().to_string(index=False))

# 필요하면 환기까지 포함된 CSV 따로 저장
vpd_vent_output = "/content/drive/MyDrive/final_project/merged_with_shading_temp_ventsim.csv"
df_with_shading.to_csv(vpd_vent_output, index=False, encoding="utf-8-sig")
print(f"[INFO] 환기 효과 포함 CSV 저장 완료: {vpd_vent_output}")

import numpy as np

# ---------------- 기본 물리 함수들 ---------------- #

def sat_vapor_pressure_kPa(T_c):
    """포화수증기압 es(T) [kPa], T_c: 섭씨온도"""
    T = np.asarray(T_c, dtype="float64")
    return 0.6108 * np.exp((17.27 * T) / (T + 237.3))

def absolute_humidity_kg_per_kg(T_c, RH_percent, P_kPa=101.3):
    """
    절대습도 w [kg H2O / kg dry air]
    T_c: 섭씨온도
    RH_percent: 상대습도 %
    """
    es = sat_vapor_pressure_kPa(T_c)
    ea = RH_percent / 100.0 * es
    return 0.622 * ea / (P_kPa - ea)

def calc_vpd_kPa(T_c, RH_percent):
    es = sat_vapor_pressure_kPa(T_c)
    ea = RH_percent / 100.0 * es
    return es - ea


# ---------------- 최적 에너지 전략 계산 함수 ---------------- #

def suggest_low_energy_vpd_control(
    T_now,
    RH_now,
    VPD_target=1.5,
    floor_area_m2=400.0,
    height_m=4.0,
    T_cool_range_deg=5.0,
    lam_kJ_per_kg=2450.0,
    cp_air_kJ_per_kgK=1.005,
    rho_air_kg_per_m3=1.2,
    verbose=True,
):
    """
    VPD_target(기본 1.5 kPa)에 도달하기 위해
    '냉방 + 가습' 조합 중 열역학적 에너지(kWh/m²)를 최소로 만드는 전략 추천.

    - T_now, RH_now : 현재 온실 상태
    - floor_area_m2 : 온실 바닥 면적
    - height_m      : 평균 높이
    - T_cool_range_deg : 최대 몇 도까지 내릴지 (예: 5°C까지)
    - verbose=True 이면 계산 과정 요약 출력(개발자용)

    반환값(dict):
      - best: {
          'T_target', 'RH_target',
          'VPD_target',
          'cooling_dT_C',
          'water_L_total',
          'water_L_per_m2',
          'q_sens_kWh_per_m2',
          'q_lat_kWh_per_m2',
          'q_tot_kWh_per_m2'
        }
    """
    # 1) 현재 상태
    VPD_now = calc_vpd_kPa(T_now, RH_now)
    es_now = sat_vapor_pressure_kPa(T_now)
    ea_now = es_now * RH_now / 100.0
    w_now = absolute_humidity_kg_per_kg(T_now, RH_now)

    volume_m3 = floor_area_m2 * height_m
    m_air = rho_air_kg_per_m3 * volume_m3  # kg dry air 라고 가정

    if verbose:
        print(f"[현재 상태] T={T_now:.2f}°C, RH={RH_now:.1f}%, VPD={VPD_now:.2f} kPa")
        print(f"[온실 규모] 바닥 {floor_area_m2:.1f} m², 높이 {height_m:.1f} m → 체적 {volume_m3:.1f} m³")
        print(f"[공기 질량] 약 {m_air:.1f} kg 가정(ρ≈{rho_air_kg_per_m3} kg/m³)")

    # 이미 목표보다 충분히 낮으면 -> 조치 필요 없음
    if VPD_now <= VPD_target + 0.05:
        if verbose:
            print("[INFO] 이미 VPD가 목표 이하입니다. 추가 냉방/가습이 꼭 필요하진 않습니다.")
        return {
            "status": "already_ok",
            "VPD_now": VPD_now,
            "VPD_target": VPD_target,
        }

    # 2) T_target 후보들을 생성 (T_now ~ T_now - T_cool_range_deg)
    T_candidates = np.linspace(T_now, max(T_now - T_cool_range_deg, 10.0), 31)

    best = None

    for T_target in T_candidates:
        es_t = sat_vapor_pressure_kPa(T_target)
        # VPD = es_t - ea_target = VPD_target → ea_target = es_t - VPD_target
        ea_target = es_t - VPD_target

        # 물리적으로 불가능한 경우(음수 수증기압)
        if ea_target <= 0:
            continue

        RH_target = ea_target / es_t * 100.0

        # RH_target > 100 이면 포화 초과 → 해당 T에서는 VPD_target 불가능
        if RH_target > 100.0:
            continue

        # 절대습도
        w_target = 0.622 * ea_target / (101.3 - ea_target)

        # humidification only (물만 추가), dehumid는 없다고 가정 → w_target >= w_now만 허용
        if w_target < w_now:
            # 이 T_target에서는 오히려 수분을 빼야하므로 스킵
            continue

        # ---------------- 에너지 계산 ---------------- #
        # 냉방(현열): T_now > T_target 일 때만
        dT = T_now - T_target
        Q_sens_kJ = m_air * cp_air_kJ_per_kgK * max(0.0, dT)
        q_sens_kWh_per_m2 = (Q_sens_kJ / 3600.0) / floor_area_m2

        # 가습(잠열 + 물량)
        delta_w = w_target - w_now             # kg H2O/kg air
        m_H2O_kg = delta_w * m_air            # kg = L
        Q_lat_kJ = m_H2O_kg * lam_kJ_per_kg
        q_lat_kWh_per_m2 = (Q_lat_kJ / 3600.0) / floor_area_m2

        q_tot = q_sens_kWh_per_m2 + q_lat_kWh_per_m2

        candidate = {
            "T_target": float(T_target),
            "RH_target": float(RH_target),
            "VPD_target": float(VPD_target),
            "cooling_dT_C": float(max(0.0, dT)),
            "water_L_total": float(m_H2O_kg),          # 온실 전체 기준 L (kg)
            "water_L_per_m2": float(m_H2O_kg / floor_area_m2),
            "q_sens_kWh_per_m2": float(q_sens_kWh_per_m2),
            "q_lat_kWh_per_m2": float(q_lat_kWh_per_m2),
            "q_tot_kWh_per_m2": float(q_tot),
        }

        if best is None or candidate["q_tot_kWh_per_m2"] < best["q_tot_kWh_per_m2"]:
            best = candidate

    if best is None:
        if verbose:
            print("[WARN] 주어진 범위 내에서 VPD_target에 도달할 수 있는 조합을 찾지 못했습니다.")
        return {
            "status": "no_feasible_solution",
            "VPD_now": VPD_now,
            "VPD_target": VPD_target,
        }

    if verbose:
        print("\n[최적 에너지 전략(열역학 기준)]")
        print(f"- 목표 온도: {best['T_target']:.2f}°C (냉방 ΔT={best['cooling_dT_C']:.2f}°C)")
        print(f"- 목표 RH:   {best['RH_target']:.1f}% → VPD ≈ {best['VPD_target']:.2f} kPa")
        print(f"- 가습량:    온실 전체 {best['water_L_total']:.1f} L (면적당 {best['water_L_per_m2']:.3f} L/m²)")
        print(f"- 에너지:    냉방 {best['q_sens_kWh_per_m2']:.4f} kWh/m², "
              f"가습(잠열) {best['q_lat_kWh_per_m2']:.4f} kWh/m²")
        print(f"            총 {best['q_tot_kWh_per_m2']:.4f} kWh/m² (열역학적 기준)")

    best["status"] = "ok"
    best["VPD_now"] = float(VPD_now)
    return best


# ---------------- 사용자 알림용 간단 출력 함수 ---------------- #

def print_user_notification(best_result):
    """
    사용자에게 보여줄 '알림용' 간단 메시지.
    (계산/물리 설명은 위 함수를 보고, 이 함수는 짧고 직관적인 안내만 담당)
    """
    status = best_result.get("status", "unknown")
    if status == "already_ok":
        print(f"[알림] 현재 VPD가 이미 목표({best_result['VPD_target']:.2f} kPa) 이하입니다. "
              "추가 냉방/가습은 크게 필요하지 않습니다.")
        return
    if status != "ok":
        print("[알림] 현재 조건에서 VPD를 목표까지 맞추는 적절한 조합을 찾지 못했습니다.")
        return

    VPD_now = best_result["VPD_now"]
    VPD_target = best_result["VPD_target"]
    dT = best_result["cooling_dT_C"]
    T_target = best_result["T_target"]
    RH_target = best_result["RH_target"]
    water_total = best_result["water_L_total"]
    water_per_m2 = best_result["water_L_per_m2"]
    q_tot = best_result["q_tot_kWh_per_m2"]

    print("[알림] VPD를 에너지 최소로 1.5 kPa에 맞추는 제어 제안입니다.")
    print(f" - 현재 VPD: {VPD_now:.2f} kPa → 목표 VPD: {VPD_target:.2f} kPa")
    print(f" - 온도는 약 {dT:.1f}°C 정도 냉방하여 {T_target:.1f}°C 근처로 맞추고,")
    print(f" - 상대습도는 약 {RH_target:.0f}% 수준이 되도록 가습하세요.")
    print(f" - 가습기 기준: 온실 전체 약 {water_total:.1f} L (면적당 {water_per_m2:.2f} L/m²) 정도 분무하면 됩니다.")
    print(f" - 이때 필요한 열에너지는 면적당 대략 {q_tot:.3f} kWh/m² 수준입니다.\n"
          "   (냉방+가습을 모두 고려한 열역학적 기준)")


# ---------------- 사용 예시 ---------------- #
if __name__ == "__main__":
    # 예: 현재 30°C, 50%, 온실 400m², 높이 4m일 때
    best = suggest_low_energy_vpd_control(
        T_now=30.0,
        RH_now=50.0,
        VPD_target=1.5,
        floor_area_m2=400.0,
        height_m=4.0,
        T_cool_range_deg=5.0,
        verbose=True  # 개발용 설명 출력
    )
    print()
    print_user_notification(best)  # 사용자용 간단 알림