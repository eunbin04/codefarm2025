# incoding.py
import os
import glob
import pandas as pd

# 선택 사항: chardet 있으면 인코딩 추정에 사용, 없으면 그냥 넘어감
try:
    import chardet
except ImportError:
    chardet = None


# ✅ 원본 CSV들이 있는 폴더
BASE_PATH = "data"

# ✅ 클린 CSV들을 저장할 폴더
OUTPUT_DIR = "data_cleaned"

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
        try:
            filename = os.path.basename(path)
        except Exception:
            filename = 'uploaded_file'
        print(f"[경고] {filename}: 인코딩이 완벽하진 않을 수 있음 (깨짐 비율 {best_bad:.2f}), 사용 enc={best_enc}")

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


bdf = pd.read_csv("data_cleaned/mc_clean.csv", encoding="utf-8-sig")
bdf.info()  # 여기 non-null 개수 보고 결측 여부 판단

bdf['date_time'] = pd.to_datetime(bdf['date_time'])
bdf.isna().sum()