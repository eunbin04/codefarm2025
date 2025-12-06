# incoding.py
import os
import glob
import pandas as pd
import sqlite3

try:
    import chardet
except ImportError:
    chardet = None


BASE_PATH = "data"
OUTPUT_DIR = "data_cleaned"

ENCODING_ORDER = ['euc-kr', 'cp949', 'utf-8-sig', 'utf-8']
SEPARATORS = [',', ';', '\t', '|', ' ']  


def detect_encoding_from_bytes(content: bytes):
    if chardet is None:
        return None
    result = chardet.detect(content)
    return result.get("encoding")


def try_read(content_bytes: bytes, encoding, sep=None):
    try:
        if sep:
            df = pd.read_csv(pd.io.common.BytesIO(content_bytes), encoding=encoding, sep=sep, engine='python')
        else:
            df = pd.read_csv(pd.io.common.BytesIO(content_bytes), encoding=encoding, engine='python')
        return df
    except:
        return None


def score_validity(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 1.0

    sample = ""
    sample += " ".join(map(str, df.columns[:10].tolist()))

    if len(df) > 0:
        sample += " " + " ".join(map(str, df.iloc[0].tolist()))

    bad = sample.count('�') + sample.count('?') + sample.count('\ufffd')
    return bad / max(len(sample), 1)


def robust_load_csv(content: bytes):
    """bytes 기반 CSV 완전 자동 판독"""
    preferred = detect_encoding_from_bytes(content)

    encodings = []

    if preferred and preferred in ENCODING_ORDER:
        encodings.append(preferred)

    for e in ENCODING_ORDER:
        if e not in encodings:
            encodings.append(e)

    candidates = []

    for enc in encodings:
        for sep in SEPARATORS:
            df = try_read(content, enc, sep)
            score = score_validity(df)
            candidates.append((score, enc, sep, df))

    candidates.sort(key=lambda x: x[0])

    best_score, best_enc, best_sep, best_df = candidates[0]

    # BOM 제거
    best_df.columns = [col.replace("\ufeff", "") for col in best_df.columns]

    # 컬럼이 1개일 경우 whitespace 강제 split
    if best_df.shape[1] < 2:
        best_df = try_read(content, best_enc, sep=r"\s+")
        if best_df is not None:
            best_df.columns = [col.replace("\ufeff", "") for col in best_df.columns]

    return best_df, best_enc, best_sep


def read_csv_robust(path_or_bytes, preferred_encoding=None):
    """
    path(str) 또는 BytesIO, 혹은 순수 bytes 모두 처리
    """
    if isinstance(path_or_bytes, str):
        with open(path_or_bytes, "rb") as f:
            content_bytes = f.read()

    elif hasattr(path_or_bytes, "read"):  # BytesIO or File-like
        content_bytes = path_or_bytes.read()

    elif isinstance(path_or_bytes, bytes):  # already bytes
        content_bytes = path_or_bytes

    else:
        raise TypeError("path_or_bytes must be bytes, file path, or file-like object")

    df, enc, sep = robust_load_csv(content_bytes)
    return df, enc


def clean_for_analysis(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]

    drop_cols = [c for c in df.columns if str(c).startswith("Unnamed")]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    df = df.replace(r'^\s*$', pd.NA, regex=True)
    return df


def make_clean_csvs_to_db(base_path: str = BASE_PATH,
                          db_path: str = 'codefarmdb.sqlite'):
    csv_files = glob.glob(os.path.join(base_path, "*.csv"))
    if not csv_files:
        print(f"[알림] '{base_path}' 에서 CSV 파일을 찾지 못했습니다.")
        return

    conn = sqlite3.connect(db_path)

    for path in csv_files:
        try:
            df_raw, enc = read_csv_robust(path)
            df_clean = clean_for_analysis(df_raw)

            table_name = os.path.splitext(os.path.basename(path))[0]

            df_clean.to_sql(table_name, conn, if_exists='replace', index=False)

            print(f"[완료] {path} → 테이블 '{table_name}', 인코딩={enc}")

        except Exception as e:
            print(f"[실패] {path} 처리 중 오류 발생: {e}")

    conn.close()
