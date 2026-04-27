import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderRateLimited
from geopy.extra.rate_limiter import RateLimiter

# 1. 페이지 설정 (미니멀리즘 스타일)
st.set_page_config(page_title="플래너", layout="wide")

# 구글 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# Geocoder 설정 및 속도 제한기 (1.5초 지연 강제)
geolocator = Nominatim(user_agent="honeymoon_planner_v20", timeout=10)
geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

# 세션 상태 초기화
if 'search_result' not in st.session_state: st.session_state.search_result = None
if 'last_clicked' not in st.session_state: st.session_state.last_clicked = None
if 'last_country' not in st.session_state: st.session_state.last_country = "유럽 전체 보기"
if 'last_city' not in st.session_state: st.session_state.last_city = "전체 보기"

# 주요 도시 절대 좌표 사전
KNOWN_CITIES = {
    "로마": (41.9028, 12.4964), "파리": (48.8566, 2.3522), "피렌체": (43.7696, 11.2558),
    "베네치아": (45.4408, 12.3155), "바르셀로나": (41.3851, 2.1734), "런던": (51.5074, -0.1278),
    "프라하": (50.0755, 14.4378), "비엔나": (48.2082, 16.3738), "인터라켄": (46.6863, 7.8632)
}

# --- 유틸리티 함수 ---
def get_country_code(name):
    name = re.sub(r'\s+', '', str(name).lower())
    mapping = {"이탈리아": "it", "프랑스": "fr", "스페인": "es", "스위스": "ch", "영국": "gb", "독일": "de"}
    return mapping.get(name, "")

def extract_coords(url):
    if not url or pd.isna(url): return None, None
    try:
        url_str = unquote(str(url))
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
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

# --- 메인 UI: 플래너 ---
st.title("💍 플래너")

# 시트 분할 (탭 기능)
tab1, tab2 = st.tabs(["📍 방문 예정지", "📅 체류 일정"])

# ==========================================
# [시트 1] 방문 예정지 (기존 수정사항 19 통합)
# ==========================================
with tab1:
    # 도시 추가 패널
    with st.expander("➕ 도시 추가", expanded=False):
        with st.form("add_city", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: add_country = st.text_input("국가")
            with c2: add_city = st.text_input("도시")
            if st.form_submit_button("등록", use_container_width=True):
                if add_country and add_city:
                    lat, lon = KNOWN_CITIES.get(add_city, (None, None))
                    if not lat:
                        try:
                            loc = geocode_with_delay(f"{add_city}, {add_country}")
                            if loc: lat, lon = loc.latitude, loc.longitude
                        except: pass
                    if lat:
                        new_row = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": f"{add_city} 중심", "구글맵 링크": f"https://www.google.com/maps?q={lat},{lon}", "카테고리": "도시"}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.cache_data.clear()
                        st.rerun()

    if not df.empty:
        col_sel, col_edit = st.columns([2, 8])
        
        with col_sel:
            countries = ["유럽 전체 보기"] + sorted(list(df["국가"].dropna().unique()))
            selected_country = st.selectbox("국가 선택", countries)
            if selected_country != st.session_state.last_country:
                st.session_state.search_result = None
                st.session_state.last_clicked = None
                st.session_state.last_country = selected_country
            
            city_list = df[df["국가"] == selected_country]["도시"].unique() if selected_country != "유럽 전체 보기" else []
            selected_city = st.selectbox("도시 선택", ["전체 보기"] + list(city_list)) if selected_country != "유럽 전체 보기" else "전체 보기"
            
            st.write("---")
            cats = ["도시", "관광지", "맛집", "숙소", "교통시설"]
            selected_cats = [cat for cat in cats if st.checkbox(cat, value=True)]

        with col_edit:
            # 검색창 (심플)
            search_q = st.text_input("🔍", placeholder="장소 검색")
            if search_q:
                try:
                    loc = geocode_with_delay(search_q)
                    if loc:
                        st.session_state.search_result = {'lat': loc.latitude, 'lon': loc.longitude, 'name': search_q}
                        st.session_state.last_clicked = None
                    else: st.warning("장소를 찾을 수 없습니다.")
                except GeocoderRateLimited: st.error("잠시 후 다시 검색해주세요.")

            # 지도 로직
            f_df = df if selected_country == "유럽 전체 보기" else df[df["국가"] == selected_country]
            if selected_city != "전체 보기": f_df = f_df[f_df["도시"] == selected_city]
            display_df = f_df[f_df["카테고리"].isin(selected_cats)]
            
            valid_points = []
            for _, r in display_df.iterrows():
                lat, lon = extract_coords(r.get("구글맵 링크", ""))
                if lat: valid_points.append({'lat': lat, 'lon': lon, 'name': r['장소명'], 'cat': r['카테고리'], 'country': r['국가'], 'city': r['도시']})
            
            # 중심점 결정
            initial_zoom = 4 if selected_country == "유럽 전체 보기" else (6 if selected_city == "전체 보기" else 13)
            if st.session_state.last_clicked: c_lat, c_lon = st.session_state.last_clicked['lat'], st.session_state.last_clicked['lng']
            elif st.session_state.search_result: c_lat, c_lon = st.session_state.search_result['lat'], st.session_state.search_result['lon']; initial_zoom = 16
            elif valid_points: c_lat, c_lon = sum(p['lat'] for p in valid_points)/len(valid_points), sum(p['lon'] for p in valid_points)/len(valid_points)
            else: c_lat, c_lon = 48.8566, 2.3522

            m = folium.Map(location=[c_lat, c_lon], zoom_start=initial_zoom)
            is_detailed = initial_zoom >= 10

            for p in valid_points:
                if p['cat'] == "도시":
                    if not is_detailed:
                        code = get_country_code(p['country'])
                        icon = folium.DivIcon(html=f'<img src="https://flagcdn.com/w40/{code}.png" style="width:34px; border-radius:4px; box-shadow:2px 2px 5px rgba(0,0,0,0.3);">') if code else folium.DivIcon(html='📍')
                        folium.Marker([p['lat'], p['lon']], tooltip=p['city'], icon=icon).add_to(m)
                else:
                    if is_detailed:
                        emj = {"맛집":"🥄", "숙소":"🏠", "교통시설":"🚆", "관광지":"📸"}.get(p['cat'], "📍")
                        icon = folium.DivIcon(html=f'<div style="font-size:32px; text-shadow: -2px 0 white, 0 2px white, 2px 0 white, 0 -2px white;">{emj}</div>')
                        folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=icon).add_to(m)
            
            # 검색/클릭 핀
            if st.session_state.search_result: folium.Marker([st.session_state.search_result['lat'], st.session_state.search_result['lon']], icon=folium.DivIcon(html='<div style="font-size:40px;">📍</div>')).add_to(m)
            if st.session_state.last_clicked: folium.Marker([st.session_state.last_clicked['lat'], st.session_state.last_clicked['lng']], icon=folium.DivIcon(html='<div style="font-size:40px;">🎯</div>')).add_to(m)

            map_out = st_folium(m, width="100%", height=750, key=f"map_{selected_country}_{selected_city}")
            if map_out and map_out.get('last_clicked'):
                if st.session_state.last_clicked != map_out['last_clicked']:
                    st.session_state.last_clicked = map_out['last_clicked']; st.session_state.search_result = None; st.rerun()

            # 저장 폼
            target = st.session_state.search_result or (st.session_state.last_clicked and {'lat':st.session_state.last_clicked['lat'], 'lon':st.session_state.last_clicked['lng'], 'name':'수동 선택 장소'})
            if target:
                with st.form("save_place"):
                    st.write(f"💾 {target.get('name', '장소')} 저장")
                    s_name = st.text_input("이름", value=target.get('name', ''))
                    s_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                    if st.form_submit_button("저장"):
                        new_row = pd.DataFrame([{"국가": selected_country if selected_country != "유럽 전체 보기" else "미정", "도시": selected_city if selected_city != "전체 보기" else "미정", "장소명": s_name, "구글맵 링크": f"https://www.google.com/maps?q={target['lat']},{target['lon']}", "카테고리": s_cat}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.session_state.search_result = st.session_state.last_clicked = None; st.cache_data.clear(); st.rerun()

            st.divider()
            st.subheader("📋")
            edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
            if st.button("💾 시트 변경사항 저장"):
                other = df[~df.index.isin(display_df.index)]
                conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
                st.cache_data.clear(); st.rerun()

# ==========================================
# [시트 2] 체류 일정 (상세 스케줄링)
# ==========================================
with tab2:
    st.subheader("📅 체류 일정")
    if not df.empty:
        # 도시 목록 가져오기
        city_rows = df[df["카테고리"] == "도시"].copy()
        if not city_rows.empty:
            st.info("각 도시별 체류 기간과 메모를 관리할 수 있습니다. (구글 시트에 '시작일', '종료일' 컬럼이 있으면 더욱 좋습니다)")
            # 엑셀 시트 형식으로 체류 일정만 별도로 편집
            st.data_editor(city_rows[["국가", "도시", "메모"]], use_container_width=True, hide_index=True)
            st.write("---")
            st.caption("💡 팁: '방문 예정지' 시트에서 장소를 검색하여 추가하면 도시별 맛집/관광지 리스트를 자동으로 쌓을 수 있습니다.")
        else:
            st.warning("등록된 도시가 없습니다. 먼저 '방문 예정지' 시트에서 도시를 추가해주세요.")
    else:
        st.info("데이터가 없습니다.")
