# incoding.py
import os
import glob
import pandas as pd

try:
    import chardet
except ImportError:
    chardet = None

BASE_PATH = "data"
OUTPUT_DIR = "data_cleaned"
TRY_ENCODINGS = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']


def guess_encoding(path, n_bytes=200000):
    if chardet is None:
        return None
    if isinstance(path, str):
        with open(path, "rb") as f:
            raw = f.read(n_bytes)
        result = chardet.detect(raw)
        return result.get("encoding")
    else:
        # 스트림일 경우 인코딩 추정 못 함
        return None


def read_csv_robust(path):
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

        text_sample = " ".join(map(str, list(df.columns)[:30]))
        if len(df) > 0:
            text_sample += " " + " ".join(map(str, df.iloc[0].astype(str).tolist()))

        bad = (text_sample.count('?') + text_sample.count('�')) / max(len(text_sample), 1)

        if bad < 0.01:
            return df, enc

        if bad < best_bad:
            best_bad = bad
            best_df = df
            best_enc = enc

    if best_df is not None:
        # 파일명 추출 안전 처리
        if isinstance(path, str):
            filename = os.path.basename(path)
        else:
            filename = getattr(path, 'name', 'uploaded_file')

        if best_bad > 0.1:
            print(f"[경고] {filename}: 인코딩이 완벽하진 않을 수 있음 (깨짐 비율 {best_bad:.2f}), 사용 enc={best_enc}")
        return best_df, best_enc

    try:
        df = pd.read_csv(path, encoding="utf-8", encoding_errors="replace")
    except Exception as e:
        if isinstance(path, str):
            filename = os.path.basename(path)
        else:
            filename = getattr(path, 'name', 'uploaded_file')
        raise RuntimeError(f"{filename}: CSV 로드 실패. 마지막 오류: {e}")

    if isinstance(path, str):
        filename = os.path.basename(path)
    else:
        filename = getattr(path, 'name', 'uploaded_file')
    print(f"[경고] {filename}: 모든 인코딩 시도 실패 → utf-8 + replace 로 강제 로드. 마지막 오류: {last_err}")
    return df, "utf-8(replace)"


def clean_for_analysis(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]

    drop_cols = [c for c in df.columns if str(c).startswith("Unnamed")]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    df = df.replace(r'^\s*$', pd.NA, regex=True)

    return df


def make_clean_csvs(base_path: str = BASE_PATH,
                    output_dir: str = OUTPUT_DIR,
                    output_encoding: str = "utf-8-sig"):
    os.makedirs(output_dir, exist_ok=True)

    csv_files = glob.glob(os.path.join(base_path, "*.csv"))
    if not csv_files:
        print(f"[알림] '{base_path}' 에서 CSV 파일을 찾지 못했습니다.")
        return

    for path in csv_files:
        if isinstance(path, str):
            filename = os.path.basename(path)
        else:
            filename = getattr(path, 'name', 'uploaded_file')

        print(f"[경고] {filename}: 인코딩이 완벽하진 않을 수 있음")

        name, ext = os.path.splitext(filename)

        if name.endswith("_clean"):
            continue

        try:
            df_raw, enc = read_csv_robust(path)
            df_clean = clean_for_analysis(df_raw)

            clean_name = f"{name}_clean{ext}"
            clean_path = os.path.join(output_dir, clean_name)

            df_clean.to_csv(clean_path, index=False, encoding=output_encoding)

            print(f"[완료] {filename} -> {clean_name} 저장 ({output_dir}) | 읽은 enc={enc} | shape={df_clean.shape}")

        except Exception as e:
            print(f"[오류] {filename} 처리 실패: {e}")


make_clean_csvs()

bdf = pd.read_csv("data_cleaned/mc_clean.csv", encoding="utf-8-sig")
bdf.info()
bdf['date_time'] = pd.to_datetime(bdf['date_time'])
bdf.isna().sum()