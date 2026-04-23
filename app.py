import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim

# 1. 페이지 설정 및 레이아웃
st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

# 구글 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# 기본 국가 좌표 (데이터가 아예 없을 때 예비용)
DEFAULT_COORDS = {
    "이탈리아": [41.8719, 12.5674], "프랑스": [46.2276, 2.2137],
    "스위스": [46.8182, 8.2275], "스페인": [40.4637, -3.7492],
    "영국": [55.3781, -3.4360], "독일": [51.1657, 10.4515]
}

geolocator = Nominatim(user_agent="honeymoon_planner_v2")

# --- 유틸리티 함수 ---

def get_country_code(name):
    """국가 이름을 분석하여 flagcdn에 사용할 2자리 코드를 반환"""
    name = str(name).strip().lower().replace(" ", "")
    mapping = {
        "이탈리아": "it", "italy": "it",
        "프랑스": "fr", "france": "fr",
        "스페인": "es", "spain": "es",
        "스위스": "ch", "switzerland": "ch",
        "영국": "gb", "unitedkingdom": "gb", "uk": "gb", "england": "gb",
        "독일": "de", "germany": "de",
        "오스트리아": "at", "austria": "at",
        "체코": "cz", "czech": "cz",
        "포르투갈": "pt", "portugal": "pt",
        "그리스": "gr", "greece": "gr"
    }
    # 매핑 테이블에 있으면 반환, 없으면 빈 문자열
    return mapping.get(name, "")

def extract_coords(url):
    """모든 형식의 구글맵 URL에서 위도/경도를 확실하게 추출"""
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    try:
        # 1. ?q=위도,경도 형식 (우리가 생성한 형식)
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url)
        if match: return float(match.group(1)), float(match.group(2))
        
        # 2. @위도,경도 형식 (구글맵 기본 형식)
        full_url = unquote(url)
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        
        # 3. !3d위도!4d경도 형식
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# --- 데이터 로드 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"시트 연결 오류: {e}")
    st.stop()

st.title("💍 2027 유럽 신혼여행 플래너")

# [수정사항 8 보강] 새로운 여행 도시 추가
with st.expander("➕ 새로운 여행 도시 추가하기", expanded=False):
    with st.form("add_city_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: add_country = st.text_input("국가 명", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시 명", placeholder="예: 피렌체")
        
        if st.form_submit_button("도시 등록", use_container_width=True):
            if add_country and add_city:
                with st.spinner(f'{add_city} 찾는 중...'):
                    location = geolocator.geocode(f"{add_city}, {add_country}")
                    if location:
                        # 좌표 추출이 가장 쉬운 표준 URL 형식으로 저장
                        auto_url = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"
                        new_row = pd.DataFrame([{
                            "국가": add_country.strip(), 
                            "도시": add_city.strip(), 
                            "장소명": f"{add_city} 중심",
                            "구글맵 링크": auto_url, 
                            "카테고리": "도시", 
                            "메모": "베이스캠프"
                        }])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("위치를 찾을 수 없습니다. 국가와 도시 이름을 정확히 입력해주세요.")

st.divider()

if not df.empty:
    col_sel, col_edit = st.columns([2, 8])

    with col_sel:
        st.subheader("📍 탐색")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        selected_country = st.selectbox("1. 국가 선택", countries)
        
        city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
        cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
        selected_city = st.selectbox("2. 도시 선택", cities)
        
        st.write("---")
        categories = ["도시", "관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_cats = [cat for cat in categories if st.checkbox(cat, value=True)]

    with col_edit:
        # 필터링
        if selected_city == "전체 보기":
            filtered_df = df[df["국가"] == selected_country].copy()
            title = f"🗺️ {selected_country} 전체"
        else:
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            title = f"🗺️ {selected_city} 상세"
        
        display_df = filtered_df[filtered_df["카테고리"].isin(selected_cats)]
        st.subheader(title)
        
        # 좌표 데이터 추출
        valid_points = []
        for _, row in display_df.iterrows():
            lat, lon = extract_coords(row.get("구글맵 링크", ""))
            if lat and lon:
                valid_points.append({
                    'lat': lat, 'lon': lon, 'name': row['장소명'], 
                    'cat': row['카테고리'], 'country': row['국가'], 'city': row['도시']
                })

        # 지도 설정
        if valid_points:
            center_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            center_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
            zoom = 6 if selected_city == "전체 보기" else 13
        else:
            center_lat, center_lon = DEFAULT_COORDS.get(selected_country, [48.8566, 2.3522])
            zoom = 6

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
        
        # 마커 그리기
        for p in valid_points:
            if p['cat'] == "도시":
                code = get_country_code(p['country'])
                if code:
                    html = f'''<div style="text-align:center;"><img src="https://flagcdn.com/w40/{code}.png" 
                             style="width:32px; border:1px solid #ddd; border-radius:4px; box-shadow:2px 2px 5px rgba(0,0,0,0.3);"></div>'''
                    icon = folium.DivIcon(html=html)
                else:
                    icon = folium.DivIcon(html=f'<div style="font-size:24px;">📍</div>')
            else:
                color = "red" if p['cat'] == "관광지" else "orange" if p['cat'] == "맛집" else "green" if p['cat'] == "숙소" else "blue"
                icon = folium.Icon(color=color, icon="info-sign")

            folium.Marker([p['lat'], p['lon']], popup=p['name'], tooltip=p['name'], icon=icon).add_to(m)
        
        st_folium(m, width="100%", height=500, key=f"map_{selected_country}_{selected_city}")

        # 데이터 관리 표
        st.divider()
        st.subheader("📋 데이터 관리")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            other = df[~df.index.isin(display_df.index)]
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
            st.success("저장 완료!")
            st.cache_data.clear()
            st.rerun()
