import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
from urllib.parse import unquote

# 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너", layout="wide")

# 1. 고정된 시트 아이디 설정
SHEET_ID = "1BVAUJ05mVkzgi2dprZ1w60b34YifUlZGxnVehPzO4aE"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

def extract_coords_from_url(url):
    """구글맵 URL에서 위도와 경도를 추출하는 함수"""
    if pd.isna(url) or not isinstance(url, str):
        return None, None
    url = unquote(url)
    # 패턴 1: @위도,경도
    match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    # 패턴 2: !3d위도!4d경도
    match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

@st.cache_data(ttl=60)
def load_and_process_data(url):
    df = pd.read_csv(url)
    # 열 이름 공백 제거
    df.columns = df.columns.str.strip()
    
    # 좌표 자동 추출 로직
    if "구글맵 링크" in df.columns:
        for idx, row in df.iterrows():
            if pd.isna(row.get("위도")) or pd.isna(row.get("경도")):
                lat, lon = extract_coords_from_url(row["구글맵 링크"])
                if lat and lon:
                    df.at[idx, "위도"] = lat
                    df.at[idx, "경도"] = lon
    return df

try:
    df = load_and_process_data(SHEET_URL)

    st.title("🇪🇺 2027 유럽 신혼여행 플래너")
    st.markdown("시트 데이터를 실시간으로 시각화합니다.")

    # 사이드바: 필터링
    st.sidebar.header("📍 여행지 탐색")
    
    if df.empty:
        st.warning("시트에 데이터가 없습니다. 국가, 도시, 장소명 등을 입력해 주세요
