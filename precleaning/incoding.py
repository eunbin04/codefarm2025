# incoding.py
import pandas as pd

TRY_ENCODINGS = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']

file_path = "data/mc.csv"  # 파일 경로 지정

def read_csv_with_encoding_try(path):
    last_err = None
    for enc in TRY_ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=enc)
            return df, enc  # 성공하면 바로 반환
        except Exception as e:
            last_err = e
            continue
    # 모두 실패하면 마지막 오류를 다시 발생
    raise RuntimeError(f"모든 인코딩 시도 실패: {last_err}")

df, encoding_used = read_csv_with_encoding_try(file_path)
print(f"읽은 인코딩: {encoding_used}")
print(df.info())