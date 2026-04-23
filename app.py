import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim

st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

geolocator = Nominatim(user_agent="honeymoon_planner_v3")

# --- 유틸리티 함수 ---
def get_country_code(name):
    """국가명을 완벽하게 필터링하여 국기 코드로 변환"""
    name = re.sub(r'\s+', '', str(name).lower()) # 모든 공백 제거 및 소문자화
    mapping = {
        "이탈리아": "it", "italy": "it",
        "프랑스": "fr", "france": "fr",
        "스페인": "es", "spain": "es",
        "스위스": "ch", "switzerland": "ch",
        "영국": "gb", "uk": "gb", "england": "gb",
        "독일": "de", "germany": "de",
        "오스트리아": "at", "austria": "at",
        "체코": "cz", "czech": "cz",
        "포르투갈": "pt", "portugal": "pt",
        "그리스": "gr", "greece": "gr"
    }
    return mapping.get(name, "")

def extract_coords(url):
    """구글맵 URL에서 좌표를 100% 확률로 추출"""
    if not url or pd.isna(url): return None, None
    try:
        url_str = unquote(str(url))
        # 1. 자체 생성 공식 (가장 확실함)
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
        # 2. 구글맵 기본 골뱅이 
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
        # 3. 모바일/특수 형식
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# --- 데이터 로드 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    df.columns = [str(c).strip() for c in df.columns]
    # 필수 컬럼이 없으면 강제 생성
    expected_cols = ["국가", "도시", "장소명", "구글맵 링크", "카테고리", "메모"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
except Exception as e:
    st.error(f"시트 연결 오류: {e}")
    st.stop()

st.title("💍 2027 유럽 신혼여행 플래너")

# ==========================================
# [신규] 1. 데이터 삭제 관리 패널
# ==========================================
with st.expander("🗑️ 데이터 강제 삭제 관리 (시트 초기화)", expanded=False):
    st.warning("⚠️ 이곳에서 삭제한 데이터는 복구할 수 없습니다.")
    del_col1, del_col2 = st.columns(2)
    
    with del_col1:
        st.subheader("특정 국가/도시 삭제")
        with st.form("delete_specific"):
            d_country = st.text_input("삭제할 국가 (예: 이탈리아)")
            d_city = st.text_input("삭제할 도시 (선택사항, 비우면 국가 전체 삭제)")
            if st.form_submit_button("해당 데이터 삭제"):
                if d_country:
                    if d_city:
                        new_df = df[~((df['국가'] == d_country) & (df['도시'] == d_city))]
                        msg = f"{d_country} {d_city} 데이터가 삭제되었습니다."
                    else:
                        new_df = df[df['국가'] != d_country]
                        msg = f"{d_country} 전체 데이터가 삭제되었습니다."
                    conn.update(spreadsheet=SHEET_URL, data=new_df)
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("국가 이름을 입력해주세요.")
                    
    with del_col2:
        st.subheader("시트 전체 백지화")
        st.info("모든 장소를 지우고 처음부터 다시 시작합니다.")
        if st.button("🚨 모든 데이터 초기화 (전체 삭제)", type="primary"):
            empty_df = pd.DataFrame(columns=["국가", "도시", "장소명", "구글맵 링크", "카테고리", "메모"])
            conn.update(spreadsheet=SHEET_URL, data=empty_df)
            st.success("시트가 완벽하게 초기화되었습니다!")
            st.cache_data.clear()
            st.rerun()

st.divider()

# ==========================================
# [수정] 3. 확실한 베이스캠프 추가 로직
# ==========================================
with st.expander("➕ 새로운 여행 도시 추가하기", expanded=True):
    with st.form("add_city_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: add_country = st.text_input("국가 명", placeholder="예: 프랑스")
        with c2: add_city = st.text_input("도시 명", placeholder="예: 파리")
        
        if st.form_submit_button("해당 도시를 지도에 핀 꽂기", use_container_width=True):
            if add_country and add_city:
                with st.spinner(f'{add_city} 좌표 찾는 중...'):
                    location = geolocator.geocode(f"{add_city}, {add_country}")
                    if location:
                        # 절대 고장나지 않는 구글맵 검색 쿼리 형식으로 저장
                        safe_url = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"
                        new_row = pd.DataFrame([{
                            "국가": add_country.strip(), 
                            "도시": add_city.strip(), 
                            "장소명": f"{add_city} 중심",
                            "구글맵 링크": safe_url, 
                            "카테고리": "도시", 
                            "메모": "여행 베이스캠프"
                        }])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.success(f"✔️ {add_city} 등록 완료! 아래 지도에서 확인하세요.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("위치를 찾을 수 없습니다. 명칭을 확인해주세요.")
            else:
                st.warning("국가와 도시를 모두 입력해주세요.")

st.divider()

if not df.empty:
    col_sel, col_edit = st.columns([2, 8])

    with col_sel:
        st.subheader("📍 탐색")
        # [수정] 2. 국가에도 '전체 보기' 추가
        raw_countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        countries = ["유럽 전체 보기"] + raw_countries
        selected_country = st.selectbox("1. 국가 선택", countries)
        
        if selected_country == "유럽 전체 보기":
            cities = ["전체 보기"]
            selected_city = "전체 보기"
            st.info("유럽 전체 지도를 표시합니다.")
        else:
            city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
            cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
            selected_city = st.selectbox("2. 도시 선택", cities)
        
        st.write("---")
        st.markdown("**🔍 카테고리 필터**")
        categories = ["도시", "관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_cats = [cat for cat in categories if st.checkbox(cat, value=True)]

    with col_edit:
        # 데이터 필터링
        if selected_country == "유럽 전체 보기":
            filtered_df = df.copy()
            title = "🗺️ 유럽 전체 신혼여행 지도"
            zoom = 4
        elif selected_city == "전체 보기":
            filtered_df = df[df["국가"] == selected_country].copy()
            title = f"🗺️ {selected_country} 전체"
            zoom = 6
        else:
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            title = f"🗺️ {selected_city} 상세"
            zoom = 12
        
        display_df = filtered_df[filtered_df["카테고리"].isin(selected_cats)]
        st.subheader(title)
        
        valid_points = []
        for _, row in display_df.iterrows():
            lat, lon = extract_coords(row.get("구글맵 링크", ""))
            if lat and lon:
                valid_points.append({
                    'lat': lat, 'lon': lon, 'name': row['장소명'], 
                    'cat': row['카테고리'], 'country': row['국가'], 'city': row['도시']
                })

        # 지도 중심 좌표 설정
        if valid_points:
            center_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            center_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
        else:
            center_lat, center_lon = 48.8566, 2.3522 # 기본 파리

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
        
        for p in valid_points:
            if p['cat'] == "도시":
                code = get_country_code(p['country'])
                if code:
                    # 윈도우 에러 방지용 이미지 국기 (가장 확실함)
                    html = f'''<div style="text-align:center;"><img src="https://flagcdn.com/w40/{code}.png" 
                             style="width:36px; border:1px solid #999; border-radius:4px; box-shadow:2px 2px 6px rgba(0,0,0,0.5);"></div>'''
                    icon = folium.DivIcon(html=html)
                else:
                    icon = folium.DivIcon(html=f'<div style="font-size:24px; text-shadow: 2px 2px 4px white;">📍</div>')
            else:
                color = "red" if p['cat'] == "관광지" else "orange" if p['cat'] == "맛집" else "green" if p['cat'] == "숙소" else "blue"
                icon = folium.Icon(color=color, icon="info-sign")

            folium.Marker([p['lat'], p['lon']], popup=p['name'], tooltip=f"[{p['country']}] {p['city']}", icon=icon).add_to(m)
        
        st_folium(m, width="100%", height=500, key=f"map_view")

        # 하단 빠른 추가
        st.write("---")
        st.subheader("🔍 세부 장소 검색 및 빠른 등록")
        search_q = st.text_input("현재 보고 있는 지역의 명소를 검색하세요 (예: 에펠탑)")
        if search_q:
            with st.spinner('위치 찾는 중...'):
                loc = geolocator.geocode(search_q)
                if loc:
                    st.success(f"📍 발견: {loc.address}")
                    with st.form("quick_add_form"):
                        q_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                        if st.form_submit_button("지도에 추가하기"):
                            new_row = pd.DataFrame([{
                                "국가": selected_country if selected_country != "유럽 전체 보기" else "미정", 
                                "도시": selected_city if selected_city != "전체 보기" else "미정",
                                "장소명": search_q, 
                                "구글맵 링크": f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}",
                                "카테고리": q_cat
                            }])
                            conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.warning("장소를 찾을 수 없습니다.")

        st.divider()
        st.subheader("📋 데이터 관리")
        edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            other = df[~df.index.isin(display_df.index)]
            conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
            st.success("저장 완료!")
            st.cache_data.clear()
            st.rerun()
else:
    st.info("데이터가 없습니다. 위쪽의 '데이터 강제 삭제 관리' 패널을 열어 초기화 하거나, 새로운 도시를 추가해주세요.")
