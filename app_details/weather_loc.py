# app_details/weather_loc.py
import pandas as pd
import streamlit as st

STATION_DIR = "data/station_code.csv"
COORDS_DIR = "data/station_loc.csv"

@st.cache_data
def load_station_table(csv_path: str = STATION_DIR) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()
    return df

@st.cache_data
def load_coords_table() -> pd.DataFrame:
    """지점코드별 위경도 테이블"""
    return pd.read_csv(COORDS_DIR)

def get_lat_lon(station_name: str) -> tuple[float, float]:
    """지점명 → 위경도 반환"""
    coords_df = load_coords_table()
    row = coords_df[coords_df["지점명"] == station_name]
    if not row.empty:
        return float(row.iloc[0]["위도"]), float(row.iloc[0]["경도"])
    return 35.8219, 127.1530  # 전주 기본값

# 기존 함수들은 그대로 (get_region_options, get_office_options 등...)
def get_region_options(df: pd.DataFrame) -> list:
    return sorted(df["지역"].dropna().unique())

def get_office_options(df: pd.DataFrame, region: str) -> list:
    df_region = df[df["지역"] == region]
    return sorted(df_region["관리관서"].dropna().unique())

def get_station_options(df: pd.DataFrame, region: str, office: str) -> list:
    df_filtered = df[(df["지역"] == region) & (df["관리관서"] == office)]
    return sorted(df_filtered["지점명"].dropna().unique())

def get_default_values(df: pd.DataFrame):
    regions = get_region_options(df)
    region_idx = regions.index("전북특별자치도") if "전북특별자치도" in regions else 0
    offices = get_office_options(df, regions[region_idx])
    office_idx = offices.index("전주기상지청") if "전주기상지청" in offices else 0
    stations = get_station_options(df, regions[region_idx], offices[office_idx])
    station_idx = stations.index("전주") if "전주" in stations else 0
    return {
        "region": "전북특별자치도", "office": "전주기상지청", "station": "전주",
        "region_idx": region_idx, "office_idx": office_idx, "station_idx": station_idx
    }
