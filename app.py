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

# 연결된 구글 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# 주요 국가별 기본 중심 좌표
COUNTRY_DEFAULT_COORDS = {
    "이탈리아": [41.8719, 12.5674], "프랑스": [46.2276, 2.2137],
    "스위스": [46.8182, 8.2275], "스페인": [40.4637, -3.7492],
    "영국": [55.3781, -3.4360], "독일": [51.1657, 10.4515],
    "오스트리아": [47.5162, 14.5501], "체코": [49.8175, 15.4730],
    "포르투갈": [39.3999, -8.2245], "그리스": [39.0742, 21.8243]
}

geolocator = Nominatim(user_agent="honeymoon_planner")

# --- 유틸리티 함수 ---

def get_long_url(short_url):
    try:
        if "goo.gl" in short_url or "maps.app.goo.gl" in short_url:
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
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# --- 데이터 연결부 ---

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"구글 시트 연결 오류: {e}")
    st.stop()

# --- 메인 UI 영역 ---

st.title("💍 2027 유럽 신혼여행 플래너")

# 베이스캠프 추가 영역
with st.expander("➕ 새로운 여행 도시 추가하기 (국가/도시만 입력)", expanded=False):
    with st.form("add_city_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: add_country = st.text_input("국가 명", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시 명", placeholder="예: 피렌체")
        
        if st.form_submit_button("해당 도시를 기본 여행지로 등록", use_container_width=True):
            if add_country and add_city:
                with st.spinner(f'{add_city}의 위치를 찾는 중...'):
                    location = geolocator.geocode(f"{add_city}, {add_country}")
                    if location:
                        auto_url = f"https://www.google.com/maps/search/?api=1&query={location.latitude},{location.longitude}"
                        new_row = pd.DataFrame([{
                            "국가": add_country, "도시": add_city, "장소명": f"{add_city} 중심",
                            "구글맵 링크": auto_url, "카테고리": "도시", "메모": "여행 베이스캠프"
                        }])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.success(f"✔️ {add_city} 등록 완료!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("도시 위치를 찾을 수 없습니다. 정확한 한글/영문 명칭을 입력해주세요.")

st.divider()

if not df.empty:
    col_sel, col_edit = st.columns([2, 8])

    with col_sel:
        st.subheader("📍 탐색/필터")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        if countries:
            selected_country = st.selectbox("1. 국가 선택", countries)
            
            city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
            cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
            selected_city = st.selectbox("2. 도시 선택", cities)
            
            st.write("---")
            st.markdown("**🔍 카테고리 필터**")
            categories = ["도시", "관광지", "맛집", "숙소", "교통시설", "기타"]
            selected_cats = [cat for cat in categories if st.checkbox(cat, value=True)]
        else:
            st.info("먼저 도시를 추가해주세요.")
            st.stop()

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
                valid_points.append({
                    'lat': lat, 'lon': lon, 'name': row['장소명'], 
                    'cat': row['카테고리'], 'city': row['도시'], 'country': row['국가']
                })

        if valid_points:
            center_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            center_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
            zoom = 6 if selected_city == "전체 보기" else 13
        else:
            center_lat, center_lon = COUNTRY_DEFAULT_COORDS.get(selected_country, [48.8566, 2.3522])
            zoom = 6

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
        
        # --- 마커 생성 및 들여쓰기 완벽 정렬 구간 ---
        for p in valid_points:
            if p['cat'] == "도시":
                # 공백을 싹 지우고 소문자로 변환한 뒤 단어 포함 여부로 철벽 검사
                raw_country = str(p['country']).lower().replace(" ", "")
                country_code = ""
                
                if "이탈리아" in raw_country or "italy" in raw_country: country_code = "it"
                elif "프랑스" in raw_country or "france" in raw_country: country_code = "fr"
                elif "스페인" in raw_country or "spain" in raw_country: country_code = "es"
                elif "스위스" in raw_country or "switzerland" in raw_country: country_code = "ch"
                elif "영국" in raw_country or "uk" in raw_country or "england" in raw_country: country_code = "gb"
                elif "독일" in raw_country or "germany" in raw_country: country_code = "de"
                elif "오스트리아" in raw_country or "austria" in raw_country: country_code = "at"
                elif "체코" in raw_country or "czech" in raw_country: country_code = "cz"
                elif "포르투갈" in raw_country or "portugal" in raw_country: country_code = "pt"
                elif "그리스" in raw_country or "greece" in raw_country: country_code = "gr"
                
                if country_code:
                    html_content = f'''
                        <div style="text-align: center;">
                            <img src="https://flagcdn.com/w40/{country_code}.png" 
                                 style="width: 32px; border: 1px solid #ddd; border-radius: 4px; box-shadow: 2px 2px 5px rgba(0,0,0,0.4);">
                        </div>
                    '''
                    custom_icon = folium.DivIcon(html=html_content)
                else:
                    # 매칭 실패 시 원인을 찾기 위해 빨간 글씨로 띄움
                    custom_icon = folium.DivIcon(html=f'<div style="font-size: 14px; color: red; font-weight: bold; text-shadow: 1px 1px 2px white;">📍{raw_country}</div>')
            
            else:
                color = "red" if p['cat'] == "관광지" else "orange" if p['cat'] == "맛집" else "green" if p['cat'] == "숙소" else "purple" if p['cat'] == "교통시설" else "blue"
                icon_shape = "camera" if p['cat'] == "관광지" else "cutlery" if p['cat'] == "맛집" else "bed" if p['cat'] == "숙소" else "info-sign"
                custom_icon = folium.Icon(color=color, icon=icon_shape)

            # 들여쓰기 완벽하게 맞춘 folium.Marker
            folium.Marker(
                [p['lat'], p['lon']], 
                popup=f"({p['city']}) {p['name']}", 
                tooltip=f"[{p['cat']}] {p['name']}", 
                icon=custom_icon
            ).add_to(m)
        # --- 마커 구간 끝 ---
        
        st_folium(m, width="100%", height=500, key=f"map_{selected_country}_{selected_city}")

        st.write("---")
        st.subheader("🔍 세부 장소 검색 및 빠른 등록")
        search_q = st.text_input("도시 내 명소를 검색하세요 (예: 피렌체 두오모 성당)")
        if search_q:
            with st.spinner('위치 찾는 중...'):
                loc = geolocator.geocode(search_q)
                if loc:
                    st.success(f"📍 발견: {loc.address}")
                    with st.form("quick_add_form"):
                        q_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                        if st.form_submit_button("현재 도시에 저장하기"):
                            new_row = pd.DataFrame([{
                                "국가": selected_country, 
                                "도시": selected_city if selected_city != "전체 보기" else "미지정",
                                "장소명": search_q, 
                                "구글맵 링크": f"https://www.google.com/maps/search/?api=1&query={loc.latitude},{loc.longitude}",
                                "카테고리": q_cat
                            }])
                            conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.warning("장소를 찾을 수 없습니다. 조금 더 구체적으로 검색해보세요.")

        st.divider()
        st.subheader("📋 데이터 관리")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            other = df[~df.index.isin(display_df.index)]
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
            st.success("시트 저장 완료!")
            st.cache_data.clear()
            st.rerun()
