import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# 1. 페이지 설정
st.set_page_config(page_title="플래너", layout="wide")

# 구글 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# Geocoder 설정
geolocator = Nominatim(user_agent="honeymoon_planner_v18", timeout=10)

# 세션 상태 초기화 (검색 및 수동 클릭 데이터 보존)
if 'search_result' not in st.session_state:
    st.session_state.search_result = None
if 'last_clicked' not in st.session_state:
    st.session_state.last_clicked = None
if 'last_country' not in st.session_state:
    st.session_state.last_country = "유럽 전체 보기"
if 'last_city' not in st.session_state:
    st.session_state.last_city = "전체 보기"

# 절대 좌표 사전
KNOWN_CITIES = {
    "로마": (41.9028, 12.4964), "파리": (48.8566, 2.3522),
    "피렌체": (43.7696, 11.2558), "베네치아": (45.4408, 12.3155),
    "밀라노": (45.4642, 9.1900), "나폴리": (40.8518, 14.2681),
    "바르셀로나": (41.3851, 2.1734), "마드리드": (40.4168, -3.7038),
    "세비야": (37.3891, -5.9845), "그라나다": (37.1773, -3.5986),
    "인터라켄": (46.6863, 7.8632), "취리히": (47.3769, 8.5417),
    "루체른": (47.0502, 8.3093), "그린델발트": (46.6242, 8.0414),
    "체르마트": (46.0207, 7.7491), "런던": (51.5074, -0.1278),
    "뮌헨": (48.1351, 11.5820), "프랑크푸르트": (50.1109, 8.6821),
    "베를린": (52.5200, 13.4050), "프라하": (50.0755, 14.4378),
    "비엔나": (48.2082, 16.3738), "빈": (48.2082, 16.3738),
    "부다페스트": (47.4979, 19.0402), "아테네": (37.9838, 23.7275),
    "산토리니": (36.3932, 25.4615)
}

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

with st.expander("🗑️ 관리", expanded=False):
    with st.form("delete_specific"):
        c_del1, c_del2 = st.columns(2)
        with c_del1: d_country = st.text_input("삭제할 국가 (예: 이탈리아)")
        with c_del2: d_city = st.text_input("삭제할 도시 (예: 로마)")
        if st.form_submit_button("해당 도시 삭제"):
            if d_country and d_city:
                try:
                    new_df = df[~((df['국가'] == d_country) & (df['도시'] == d_city))]
                    conn.update(spreadsheet=SHEET_URL, data=new_df)
                    st.success(f"{d_city} 삭제 완료!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error("구글 서버 제한입니다. 1분 후 시도해주세요.")
            else:
                st.error("국가와 도시를 모두 입력해주세요.")
                
    st.write("---")
    if st.button("🚨 전체 데이터 초기화", type="primary"):
        empty_df = pd.DataFrame(columns=["국가", "도시", "장소명", "구글맵 링크", "카테고리", "메모"])
        conn.update(spreadsheet=SHEET_URL, data=empty_df)
        st.session_state.search_result = None
        st.session_state.last_clicked = None
        st.cache_data.clear()
        st.rerun()

with st.expander("➕ 도시 추가", expanded=True):
    with st.form("add_city", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: add_country = st.text_input("국가", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시", placeholder="예: 피렌체")
        if st.form_submit_button("등록", use_container_width=True):
            if add_country and add_city:
                city_key = add_city.strip()
                try:
                    if city_key in KNOWN_CITIES:
                        lat, lon = KNOWN_CITIES[city_key]
                        safe_url = f"https://www.google.com/maps?q={lat},{lon}"
                    else:
                        with st.spinner(f'{add_city} 좌표 찾는 중...'):
                            location = geolocator.geocode(f"{add_city}, {add_country}")
                            if location:
                                safe_url = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"
                            else:
                                st.error("위치를 찾을 수 없습니다.")
                                st.stop()
                    
                    new_row = pd.DataFrame([{"국가": add_country.strip(), "도시": city_key, "장소명": f"{city_key} 중심", "구글맵 링크": safe_url, "카테고리": "도시", "메모": "베이스캠프"}])
                    conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 한도 초과: 1분 뒤에 다시 시도해주세요.")

st.divider()

if not df.empty:
    col_sel, col_edit = st.columns([2, 8])

    with col_sel:
        st.subheader("📍")
        countries = ["유럽 전체 보기"] + sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        selected_country = st.selectbox("국가", countries)
        
        # 국가 변경 시 세션 초기화
        if selected_country != st.session_state.last_country:
            st.session_state.search_result = None
            st.session_state.last_clicked = None
            st.session_state.last_country = selected_country
        
        if selected_country == "유럽 전체 보기":
            selected_city = "전체 보기"
        else:
            city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
            cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
            selected_city = st.selectbox("도시", cities)
            
            # 도시 변경 시 세션 초기화
            if selected_city != st.session_state.last_city:
                st.session_state.search_result = None
                st.session_state.last_clicked = None
                st.session_state.last_city = selected_city
        
        st.write("---")
        cats = ["도시", "관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_cats = [cat for cat in cats if st.checkbox(cat, value=True)]

    with col_edit:
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
        
        search_q = st.text_input("🔍", placeholder="정확도를 위해 '도시명+장소'로 검색 (예: 파리 에펠탑)")
        if search_q:
            with st.spinner('🔍 검색 중...'):
                try:
                    loc = geolocator.geocode(search_q)
                    if loc:
                        st.session_state.search_result = {'lat': loc.latitude, 'lon': loc.longitude, 'name': search_q}
                        st.session_state.last_clicked = None # 검색 시 수동 클릭 초기화
                        initial_zoom = 16
                    else:
                        st.session_state.search_result = None
                        st.warning("❌ 장소를 찾을 수 없습니다.")
                except GeocoderTimedOut:
                    st.error("접속 지연입니다. 잠시 후 다시 검색해주세요.")
        
        valid_points = []
        for _, row in display_df.iterrows():
            lat, lon = extract_coords(row.get("구글맵 링크", ""))
            if lat and lon:
                valid_points.append({'lat': lat, 'lon': lon, 'name': row['장소명'], 'cat': row['카테고리'], 'country': row['국가'], 'city': row['도시']})

        # 🎯 지도 중심 설정 (수동 클릭 > 검색 결과 > 절대 좌표 > 평균 좌표)
        if st.session_state.last_clicked:
            c_lat, c_lon = st.session_state.last_clicked['lat'], st.session_state.last_clicked['lng']
        elif st.session_state.search_result:
            c_lat, c_lon = st.session_state.search_result['lat'], st.session_state.search_result['lon']
        elif selected_city in KNOWN_CITIES:  
            c_lat, c_lon = KNOWN_CITIES[selected_city]
        elif valid_points:
            c_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            c_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
        else:
            c_lat, c_lon = 48.8566, 2.3522

        m = folium.Map(location=[c_lat, c_lon], zoom_start=initial_zoom)
        is_detailed = initial_zoom >= 10

        # 기존 마커 그리기
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
                    icon_html = f'<div style="font-size:32px; filter: drop-shadow(2px 2px 2px rgba(0,0,0,0.5)); text-shadow: -2px 0 white, 0 2px white, 2px 0 white, 0 -2px white;">{emj}</div>'
                    folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=folium.DivIcon(html=icon_html)).add_to(m)
        
        # 검색 결과 핀 (빨간색)
        if st.session_state.search_result and not st.session_state.last_clicked:
            res = st.session_state.search_result
            folium.Marker([res['lat'], res['lon']], tooltip="검색 결과", icon=folium.DivIcon(html=f'<div style="font-size:40px; filter: drop-shadow(0 0 5px red);">📍</div>')).add_to(m)
        
        # [핵심] 수동 클릭 타겟 핀 (파란색 다트)
        if st.session_state.last_clicked:
            clk = st.session_state.last_clicked
            folium.Marker([clk['lat'], clk['lng']], tooltip="내가 선택한 위치", icon=folium.DivIcon(html=f'<div style="font-size:40px; filter: drop-shadow(0 0 5px blue);">🎯</div>')).add_to(m)
        
        # 지도 출력 및 클릭 이벤트 수신
        map_output = st_folium(m, width="100%", height=750, key=f"map_{selected_country}_{selected_city}")

        # [핵심 로직] 지도 클릭 시 검색 무시하고 수동 모드로 즉시 전환
        if map_output and map_output.get('last_clicked'):
            current_click = map_output['last_clicked']
            # 사용자가 방금 새로 지도를 클릭했다면?
            if st.session_state.get('last_clicked') != current_click:
                st.session_state.last_clicked = current_click
                st.session_state.search_result = None # 기존 검색 결과 덮어쓰기!
                st.rerun() # 화면 즉시 새로고침

        # 폼 출력 영역
        if st.session_state.search_result:
            with st.form("quick_add_form"):
                st.write(f"💾 **{st.session_state.search_result['name']}** 저장")
                q_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                if st.form_submit_button("현재 도시에 저장"):
                    try:
                        res = st.session_state.search_result
                        new_row = pd.DataFrame([{"국가": selected_country if selected_country != "유럽 전체 보기" else "미정", "도시": selected_city if selected_city != "전체 보기" else "미정", "장소명": res['name'], "구글맵 링크": f"https://www.google.com/maps?q={res['lat']},{res['lon']}", "카테고리": q_cat}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.session_state.search_result = None
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error("저장 한도(1분 60회) 초과: 1분 뒤 다시 눌러주세요.")
                        
        elif st.session_state.last_clicked:
            c_lat = st.session_state.last_clicked['lat']
            c_lng = st.session_state.last_clicked['lng']
            st.info(f"👆 지도 클릭 감지! 정확한 위치에 🎯 마커가 생겼습니다.")
            
            with st.form("manual_add_form"):
                m_name = st.text_input("장소 이름", placeholder="직접 클릭한 장소의 이름을 적어주세요")
                m_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                
                # 취소 버튼과 저장 버튼 나란히 배치
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.form_submit_button("취소하기", use_container_width=True):
                        st.session_state.last_clicked = None
                        st.rerun()
                with col_btn2:
                    if st.form_submit_button("이 좌표로 장소 저장하기", type="primary", use_container_width=True):
                        try:
                            manual_url = f"https://www.google.com/maps?q={c_lat},{c_lng}"
                            new_row = pd.DataFrame([{"국가": selected_country if selected_country != "유럽 전체 보기" else "미정", "도시": selected_city if selected_city != "전체 보기" else "미정", "장소명": m_name if m_name else "수동 지정 장소", "구글맵 링크": manual_url, "카테고리": m_cat, "메모": "지도 클릭으로 직접 지정함"}])
                            conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                            st.session_state.last_clicked = None # 완료 후 클릭 상태 해제
                            st.success("수동 지정 위치 저장 완료!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error("저장 한도 초과: 1분 뒤 다시 시도해주세요.")

        st.divider()
        st.subheader("📋")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 저장", type="primary", use_container_width=True):
            try:
                other = df[~df.index.isin(display_df.index)]
                conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error("저장 한도 초과: 1분만 기다리셨다가 저장해주세요!")
else:
    st.info("상단의 '도시 추가' 패널을 열어 첫 번째 여행지를 등록해주세요.")
