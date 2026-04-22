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
        st.warning("시트에 데이터가 없습니다. 국가, 도시, 장소명 등을 입력해 주세요.")
        st.stop()

    countries = sorted(df["국가"].dropna().unique())
    selected_country = st.sidebar.selectbox("1. 국가 선택", countries)

    cities = sorted(df[df["국가"] == selected_country]["도시"].dropna().unique())
    selected_city = st.sidebar.selectbox("2. 도시 선택", cities)

    # 데이터 필터링
    filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)]

    # 메인 화면: 지도 및 목록
    col1, col2 = st.columns([1.5, 1])

    with col1:
        st.subheader(f"🗺️ {selected_city} 지도")
        # 좌표가 있는 데이터만 선별
        map_data = filtered_df.dropna(subset=["위도", "경도"])
        
        if not map_data.empty:
            m = folium.Map(location=[map_data["위도"].mean(), map_data["경도"].mean()], zoom_start=13)
            for _, row in map_data.iterrows():
                priority = row.get("우선순위", 0)
                folium.Marker(
                    [row["위도"], row["경도"]],
                    popup=row.get("장소명", "Point"),
                    tooltip=f"{row.get('장소명')} ({row.get('카테고리', '미분류')})",
                    icon=folium.Icon(color="red" if priority >= 5 else "blue")
                ).add_to(m)
            st_folium(m, width="100%", height=500)
        else:
            st.info("💡 구글맵 링크를 입력하면 지도가 활성화됩니다.")

    with col2:
        st.subheader("📋 장소 목록")
        # 보기 편하게 주요 열만 표시
        cols_to_show = [c for c in ["장소명", "카테고리", "우선순위", "메모"] if c in filtered_df.columns]
        st.dataframe(filtered_df[cols_to_show].sort_values(by="우선순위", ascending=False) if "우선순위" in cols_to_show else filtered_df[cols_to_show], 
                     use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"연결 중 오류가 발생했습니다: {e}")
