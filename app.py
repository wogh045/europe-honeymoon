import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim

# 1. 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# 주요 국가별 기본 중심 좌표 (데이터가 아예 없을 때의 예비용)
COUNTRY_DEFAULT_COORDS = {
    "이탈리아": [41.8719, 12.5674], "프랑스": [46.2276, 2.2137],
    "스위스": [46.8182, 8.2275], "스페인": [40.4637, -3.7492],
    "영국": [55.3781, -3.4360], "독일": [51.1657, 10.4515]
}

geolocator = Nominatim(user_agent="honeymoon_planner")

def get_long_url(short_url):
    try:
        if "goo.gl" in short_url or "www.google.com/maps" in short_url:
            response = requests.head(short_url, allow_redirects=True, timeout=5)
            return response.url
        return short_url
    except: return short_url

def extract_coords(url):
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    full_url = unquote(get_long_url(url))
    try:
        # 다양한 구글맵 좌표 패턴 대응
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# 데이터 연결 (ttl=600으로 API 제한 방지)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

st.title("💍 2027 유럽 신혼여행 플래너")

# [수정사항 8] 최상단: 도시 단위 빠른 추가 (국가/도시만 입력)
with st.expander("➕ 새로운 여행 도시 추가하기 (좌표 자동 생성)", expanded=False):
    with st.form("add_city_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: add_country = st.text_input("국가 명", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시 명", placeholder="예: 피렌체")
        
        if st.form_submit_button("해당 도시를 기본 여행지로 등록", use_container_width=True):
            if add_country and add_city:
                with st.spinner(f'{add_city}의 위치를 찾는 중...'):
                    # geopy를 이용해 도시 좌표 검색
                    location = geolocator.geocode(f"{add_city}, {add_country}")
                    if location:
                        # 구글맵 링크 자동 생성 (좌표 기반)
                        auto_url = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"
                        new_row = pd.DataFrame([{
                            "국가": add_country,
                            "도시": add_city,
                            "장소명": f"{add_city} 중심", # 장소명을 도시 중심으로 설정
                            "구글맵 링크": auto_url,
                            "카테고리": "도시", # 요청하신 대로 카테고리는 고정
                            "메모": "여행 베이스캠프"
                        }])
                        updated_df = pd.concat([df, new_row], ignore_index=True)
                        conn.update(spreadsheet=SHEET_URL, data=updated_df)
                        st.success(f"✔️ {add_city}가 성공적으로 등록되었습니다! 이제 지도로 확인해보세요.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("도시 위치를 찾을 수 없습니다. 정확한 명칭인지 확인해주세요.")
            else:
                st.warning("국가와 도시 이름을 모두 입력해주세요.")

st.divider()

# [중단] 레이아웃 (2:8 비율 유지)
if not df.empty:
    col_sel, col_edit = st.columns([2, 8])

    with col_sel:
        st.subheader("📍 탐색/필터")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        selected_country = st.selectbox("1. 국가 선택", countries)
        
        city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
        cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
        selected_city = st.selectbox("2. 도시 선택", cities)
        
        st.write("---")
        st.markdown("**🔍 카테고리 필터**")
        # [수정] 필터 항목에 '도시' 추가
        categories = ["도시", "관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_cats = [cat for cat in categories if st.checkbox(cat, value=True)]

    with col_edit:
        if selected_city == "전체 보기":
            filtered_df = df[df["국가"] == selected_country].copy()
            title_text = f"🗺️ {selected_country} 전체 현황"
        else:
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            title_text = f"🗺️ {selected_city} 상세 정보"
        
        display_df = filtered_df[filtered_df["카테고리"].isin(selected_cats)]

        st.subheader(title_text)
        valid_points = []
        for _, row in display_df.iterrows():
            lat, lon = extract_coords(row.get("구글맵 링크", ""))
            if lat and lon:
                valid_points.append({'lat': lat, 'lon': lon, 'name': row['장소명'], 'cat': row['카테고리'], 'city': row['도시']})

        # 지도 중심 설정 로직
        if valid_points:
            center_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            center_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
            zoom = 6 if selected_city == "전체 보기" else 13
        else:
            center_lat, center_lon = COUNTRY_DEFAULT_COORDS.get(selected_country, [48.8566, 2.3522])
            zoom = 6

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
        for p in valid_points:
            # 카테고리별 마커 색상 (도시 카테고리는 검정색으로 구분)
            color = "black" if p['cat'] == "도시" else "red" if p['cat'] == "관광지" else "orange" if p['cat'] == "맛집" else "green" if p['cat'] == "숙소" else "blue"
            folium.Marker(
                [p['lat'], p['lon']], 
                popup=f"({p['city']}) {p['name']}", 
                tooltip=f"[{p['cat']}] {p['name']}", 
                icon=folium.Icon(color=color, icon='university' if p['cat'] == "도시" else 'info-sign')
            ).add_to(m)
        
        st_folium(m, width="100%", height=500, key=f"map_{selected_country}_{selected_city}")

        # [하단] 장소 검색 섹션 (기존 유지)
        st.write("---")
        st.subheader("🔍 세부 장소 검색 (맛집/숙소 등)")
        search_query = st.text_input("도시 내에서 찾고 싶은 장소를 입력하세요", placeholder="예: 피렌체 티본스테이크 맛집")
        if search_query:
            location = geolocator.geocode(search_query)
            if location:
                st.success(f"📍 검색 결과: {location.address}")
                with st.form("quick_add"):
                    q_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설"])
                    if st.form_submit_button("현재 도시에 바로 추가"):
                        new_row = pd.DataFrame([{
                            "국가": selected_country, "도시": selected_city if selected_city != "전체 보기" else "미지정",
                            "장소명": search_query, "구글맵 링크": f"https://www.google.com/maps?q={location.latitude},{location.longitude}",
                            "카테고리": q_cat
                        }])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.cache_data.clear()
                        st.rerun()

        st.divider()
        st.subheader("📋 데이터 관리")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            other = df[~df.index.isin(display_df.index)]
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
            st.success("저장되었습니다!")
            st.cache_data.clear()
            st.rerun()
