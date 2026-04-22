import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection

# 1. 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# [추가] 주요 국가별 기본 중심 좌표 (데이터가 없을 때 지도를 띄우는 용도)
COUNTRY_DEFAULT_COORDS = {
    "이탈리아": [41.8719, 12.5674],
    "프랑스": [46.2276, 2.2137],
    "스위스": [46.8182, 8.2275],
    "스페인": [40.4637, -3.7492],
    "영국": [55.3781, -3.4360],
    "독일": [51.1657, 10.4515],
    "오스트리아": [47.5162, 14.5501],
    "체코": [49.8175, 15.4730],
    "포르투갈": [39.3999, -8.2245],
    "그리스": [39.0742, 21.8243]
}

def get_long_url(short_url):
    try:
        if "goo.gl" in short_url or "http://googleusercontent.com/maps.google.com/6" in short_url:
            response = requests.head(short_url, allow_redirects=True, timeout=5)
            return response.url
        return short_url
    except: return short_url

def extract_coords(url):
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    full_url = unquote(get_long_url(url))
    try:
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# 데이터 로드
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=0)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

st.title("💍 2027 유럽 신혼여행 플래너")

# [상단] 새로운 여행지 추가 탭
with st.expander("➕ 새로운 여행지 추가하기"):
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: add_country = st.text_input("국가", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시", placeholder="예: 로마")
        with c3: add_place = st.text_input("장소명")
        c4, c5 = st.columns([3, 1])
        with c4: add_url = st.text_input("구글맵 링크")
        with c5: add_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
        if st.form_submit_button("저장하기"):
            new_row = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": add_place, "구글맵 링크": add_url, "카테고리": add_cat}])
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
            st.cache_data.clear()
            st.rerun()

st.divider()

# [중단] 지도 및 관리 레이아웃
if not df.empty:
    col_sel, col_edit = st.columns([1, 3])

    with col_sel:
        st.subheader("📍 여행지 탐색")
        countries = sorted(list(df["국가"].dropna().unique()))
        selected_country = st.selectbox("1. 국가 선택", countries)
        
        cities = ["전체 보기"] + sorted(list(df[df["국가"] == selected_country]["도시"].dropna().unique()))
        selected_city = st.selectbox("2. 도시 선택", cities)
        
        st.write("---")
        st.markdown("**🔍 필터**")
        categories = ["관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_cats = [cat for cat in categories if st.checkbox(cat, value=True)]

    with col_edit:
        # 데이터 필터링
        if selected_city == "전체 보기":
            filtered_df = df[df["국가"] == selected_country].copy()
        else:
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
        
        display_df = filtered_df[filtered_df["카테고리"].isin(selected_cats)]

        # [핵심 로직] 지도 그리기
        st.subheader(f"🗺️ {selected_country} - {selected_city}")
        
        # 1. 마커용 좌표 추출
        valid_points = []
        for _, row in display_df.iterrows():
            lat, lon = extract_coords(row.get("구글맵 링크", ""))
            if lat and lon:
                valid_points.append({'lat': lat, 'lon': lon, 'name': row['장소명'], 'cat': row['카테고리'], 'city': row['도시']})

        # 2. 중심점 결정 (데이터가 있으면 데이터 중심, 없으면 국가 기본 중심)
        if valid_points:
            center_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            center_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
            zoom = 6 if selected_city == "전체 보기" else 13
        else:
            # 데이터가 없을 때 미리 정의한 국가 좌표 사용
            center_lat, center_lon = COUNTRY_DEFAULT_COORDS.get(selected_country, [48.8566, 2.3522]) # 기본은 파리
            zoom = 6 # 국가 단위로 넓게 보여줌

        # 3. 지도 생성 및 마커 추가
        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
        for p in valid_points:
            color = "red" if p['cat'] == "관광지" else "orange" if p['cat'] == "맛집" else "green" if p['cat'] == "숙소" else "blue"
            folium.Marker([p['lat'], p['lon']], popup=f"({p['city']}) {p['name']}", icon=folium.Icon(color=color)).add_to(m)
        
        st_folium(m, width="100%", height=500, key=f"map_{selected_country}_{selected_city}")

        st.divider()
        st.subheader("📋 데이터 편집")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            other = df[~df.index.isin(display_df.index)]
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
            st.cache_data.clear()
            st.rerun()
