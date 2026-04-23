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
st.set_page_config(page_title="플래너", layout="wide")

# 구글 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# Geocoder 설정
geolocator = Nominatim(user_agent="honeymoon_planner_v13")

# 세션 상태 초기화 (검색 결과 유지용)
if 'search_result' not in st.session_state:
    st.session_state.search_result = None

# --- 유틸리티 함수 ---
def get_country_code(name):
    name = re.sub(r'\s+', '', str(name).lower())
    mapping = {
        "이탈리아": "it", "italy": "it", "프랑스": "fr", "france": "fr",
        "스페인": "es", "spain": "es", "스위스": "ch", "switzerland": "ch",
        "영국": "gb", "uk": "gb", "독일": "de", "germany": "de",
        "오스트리아": "at", "austria": "at", "체코": "cz", "czech": "cz",
        "포르투갈": "pt", "portugal": "pt", "그리스": "gr", "greece": "gr"
    }
    return mapping.get(name, "")

def extract_coords(url):
    if not url or pd.isna(url): return None, None
    try:
        url_str = unquote(str(url))
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# --- 데이터 로드 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

# --- UI 영역 ---
st.title("💍 플래너")

# 관리 패널
with st.expander("🗑️ 관리", expanded=False):
    if st.button("🚨 전체 데이터 초기화", type="primary"):
        empty_df = pd.DataFrame(columns=["국가", "도시", "장소명", "구글맵 링크", "카테고리", "메모"])
        conn.update(spreadsheet=SHEET_URL, data=empty_df)
        st.session_state.search_result = None
        st.cache_data.clear()
        st.rerun()

# 도시 추가
with st.expander("➕ 도시 추가", expanded=True):
    with st.form("add_city", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: add_country = st.text_input("국가", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시", placeholder="예: 피렌체")
        if st.form_submit_button("등록", use_container_width=True):
            if add_country and add_city:
                location = geolocator.geocode(f"{add_city}, {add_country}")
                if location:
                    safe_url = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"
                    new_row = pd.DataFrame([{"국가": add_country.strip(), "도시": add_city.strip(), "장소명": f"{add_city} 중심", "구글맵 링크": safe_url, "카테고리": "도시", "메모": "베이스캠프"}])
                    conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                    st.cache_data.clear()
                    st.rerun()

st.divider()

if not df.empty:
    col_sel, col_edit = st.columns([2, 8])

    with col_sel:
        st.subheader("📍")
        countries = ["유럽 전체 보기"] + sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        selected_country = st.selectbox("국가", countries)
        
        if selected_country == "유럽 전체 보기":
            selected_city = "전체 보기"
        else:
            city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
            cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
            selected_city = st.selectbox("도시", cities)
        
        st.write("---")
        cats = ["도시", "관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_cats = [cat for cat in cats if st.checkbox(cat, value=True)]

    with col_edit:
        # 기본 줌 설정
        if selected_country == "유럽 전체 보기":
            filtered_df = df.copy()
            initial_zoom = 4
        elif selected_city == "전체 보기":
            filtered_df = df[df["국가"] == selected_country].copy()
            initial_zoom = 6
        else:
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            initial_zoom = 13
        
        display_df = filtered_df[filtered_df["카테고리"].isin(selected_cats)]
        
        # [검색 기능 로직]
        st.write("---")
        search_q = st.text_input("🔍", placeholder="장소 검색 (검색 후 엔터)")
        
        if search_q:
            with st.spinner('🔍 검색 중...'):
                loc = geolocator.geocode(search_q)
                if loc:
                    st.session_state.search_result = {
                        'lat': loc.latitude, 'lon': loc.longitude, 
                        'name': search_q, 'address': loc.address
                    }
                    st.success(f"✔️ 발견: {loc.address[:60]}...")
                    initial_zoom = 16 # 찾으면 줌인
                else:
                    st.session_state.search_result = None
                    st.warning("❌ 해당 장소를 찾을 수 없습니다.")

        st.subheader("🗺️")
        
        # 좌표 데이터 준비
        valid_points = []
        for _, row in display_df.iterrows():
            lat, lon = extract_coords(row.get("구글맵 링크", ""))
            if lat and lon:
                valid_points.append({'lat': lat, 'lon': lon, 'name': row['장소명'], 'cat': row['카테고리'], 'country': row['국가'], 'city': row['도시']})

        # 지도 중심 결정 (검색 결과가 있으면 우선순위)
        if st.session_state.search_result:
            c_lat = st.session_state.search_result['lat']
            c_lon = st.session_state.search_result['lon']
        elif valid_points:
            c_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            c_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
        else:
            c_lat, c_lon = 48.8566, 2.3522

        m = folium.Map(location=[c_lat, c_lon], zoom_start=initial_zoom)
        
        # 가시성 판단 (줌 레벨 10 이상일 때만 상세 장소 노출)
        is_detailed = initial_zoom >= 10

        # 저장된 마커 그리기
        for p in valid_points:
            if p['cat'] == "도시":
                if not is_detailed:
                    code = get_country_code(p['country'])
                    icon_html = f'<img src="https://flagcdn.com/w40/{code}.png" style="width:34px; border:2px solid white; border-radius:4px; box-shadow:2px 2px 5px rgba(0,0,0,0.3);">' if code else '📍'
                    folium.Marker([p['lat'], p['lon']], tooltip=p['city'], icon=folium.DivIcon(html=icon_html)).add_to(m)
            else:
                if is_detailed:
                    if p['cat'] == "맛집": emj = "🥄"
                    elif p['cat'] == "숙소": emj = "🏠"
                    elif p['cat'] == "교통시설": emj = "🚆"
                    elif p['cat'] == "관광지": emj = "📸"
                    else: emj = "📍"
                    # 크기 고정 및 그림자 보강 (글자 외곽선 효과)
                    icon_html = f'<div style="font-size:32px; filter: drop-shadow(2px 2px 2px rgba(0,0,0,0.5)); text-shadow: -2px 0 white, 0 2px white, 2px 0 white, 0 -2px white;">{emj}</div>'
                    folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=folium.DivIcon(html=icon_html)).add_to(m)
        
        # 검색된 장소 임시 마커 표시
        if st.session_state.search_result:
            res = st.session_state.search_result
            folium.Marker(
                [res['lat'], res['lon']], 
                tooltip="검색된 장소", 
                icon=folium.DivIcon(html=f'<div style="font-size:40px; filter: drop-shadow(0 0 5px red);">📍</div>')
            ).add_to(m)
        
        st_folium(m, width="100%", height=750, key="map")

        # 저장 폼 (검색 결과가 있을 때만 등장)
        if st.session_state.search_result:
            with st.form("quick_add_form"):
                st.write(f"💾 **'{st.session_state.search_result['name']}'** 장소를 저장하시겠습니까?")
                q_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                if st.form_submit_button("현재 도시에 저장"):
                    res = st.session_state.search_result
                    new_row = pd.DataFrame([{
                        "국가": selected_country if selected_country != "유럽 전체 보기" else "미정", 
                        "도시": selected_city if selected_city != "전체 보기" else "미정", 
                        "장소명": res['name'], 
                        "구글맵 링크": f"https://www.google.com/maps?q={res['lat']},{res['lon']}", 
                        "카테고리": q_cat
                    }])
                    conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                    st.session_state.search_result = None
                    st.cache_data.clear()
                    st.rerun()

        st.divider()
        st.subheader("📋")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            other = df[~df.index.isin(display_df.index)]
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
            st.cache_data.clear()
            st.rerun()
else:
    st.info("도시를 추가해주세요.")
