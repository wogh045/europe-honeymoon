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

# 연결된 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

def get_long_url(short_url):
    """짧은 URL을 긴 URL로 변환 (좌표 추출용)"""
    try:
        if "goo.gl" in short_url or "maps.app.goo.gl" in short_url:
            response = requests.head(short_url, allow_redirects=True, timeout=5)
            return response.url
        return short_url
    except:
        return short_url

def extract_coords(url):
    """URL에서 위도/경도 추출"""
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    full_url = unquote(get_long_url(url))
    try:
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
    except:
        pass
    return None, None

# 데이터 연결 및 로드
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=0)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

# --- UI 레이아웃 시작 ---
st.title("💍 2027 유럽 신혼여행 플래너")

# [수정 1] 최상단: 새로운 여행지 추가 탭
with st.expander("➕ 새로운 여행지 추가하기", expanded=False):
    with st.form("add_new_place", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: add_country = st.text_input("국가", placeholder="예: 프랑스")
        with c2: add_city = st.text_input("도시", placeholder="예: 파리")
        with c3: add_place = st.text_input("장소명", placeholder="예: 에펠탑")
        
        c4, c5 = st.columns([3, 1])
        with c4: add_url = st.text_input("구글맵 링크", placeholder="짧은 주소도 가능합니다")
        with c5: 
            # [수정] 우선순위 삭제, 카테고리 선택 항목 추가
            add_category = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
        
        if st.form_submit_button("시트에 저장하기", use_container_width=True):
            if add_country and add_city and add_place:
                new_row = pd.DataFrame([{
                    "국가": add_country, 
                    "도시": add_city, 
                    "장소명": add_place, 
                    "구글맵 링크": add_url, 
                    "카테고리": add_category,
                    "우선순위": 3 # 내부 데이터 유지를 위해 기본값 3 부여
                }])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=updated_df)
                st.success(f"'{add_place}'({add_category})가 성공적으로 저장되었습니다!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("국가, 도시, 장소명은 반드시 입력해야 합니다.")

st.divider()

# [수정 2] 중단: 좌측(선택) / 우측(관리) 레이아웃
if not df.empty:
    main_left, main_right = st.columns([1, 3])

    with main_left:
        st.subheader("📍 여행지 선택")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        if countries:
            # 국가와 도시를 상하로 배치
            sel_country = st.selectbox("1. 국가 선택", countries)
            
            city_list = df[df["국가"] == sel_country]["도시"].dropna().unique()
            cities = sorted([c for c in city_list if str(c).strip()])
            
            if cities:
                sel_city = st.selectbox("2. 도시 선택", cities)
                filtered_df = df[(df["국가"] == sel_country) & (df["도시"] == sel_city)].copy()
            else:
                st.info("도시를 등록해주세요.")
                filtered_df = pd.DataFrame()
        else:
            st.info("국가를 등록해주세요.")
            filtered_df = pd.DataFrame()

    with main_right:
        st.subheader("📋 장소 관리")
        if not filtered_df.empty:
            edited_df = st.data_editor(
                filtered_df, 
                use_container_width=True, 
                hide_index=True, 
                num_rows="dynamic"
            )
            
            if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
                other_data = df[~((df["국가"] == sel_country) & (df["도시"] == sel_city))]
                final_data = pd.concat([other_data, edited_df], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=final_data)
                st.success("데이터가 성공적으로 업데이트되었습니다.")
                st.cache_data.clear()
                st.rerun()
        else:
            st.write("도시를 선택하면 장소 목록이 여기에 나타납니다.")

    # 하단: 지도
    if not filtered_df.empty:
        st.divider()
        st.subheader(f"🗺️ {sel_city} 여행 지도")
        valid_points = []
        with st.spinner('좌표를 가져오는 중입니다...'):
            for _, row in filtered_df.iterrows():
                lat, lon = extract_coords(row.get("구글맵 링크", ""))
                if lat and lon:
                    valid_points.append({
                        'lat': lat, 'lon': lon, 
                        'name': row.get('장소명', '장소'),
                        'cat': row.get('카테고리', '기타')
                    })
        
        if valid_points:
            avg_lat = sum(p['lat'] for p in valid_points) / len(valid_points)
            avg_lon = sum(p['lon'] for p in valid_points) / len(valid_points)
            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)
            
            # 카테고리별 마커 색상 구분
            for p in valid_points:
                color = "blue"
                if p['cat'] == "맛집": color = "orange"
                elif p['cat'] == "숙소": color = "green"
                elif p['cat'] == "관광지": color = "red"
                elif p['cat'] == "교통시설": color = "purple"
                
                folium.Marker(
                    [p['lat'], p['lon']],
                    popup=f"[{p['cat']}] {p['name']}",
                    tooltip=p['name'],
                    icon=folium.Icon(color=color, icon='info-sign')
                ).add_to(m)
            st_folium(m, width="100%", height=500, key=f"map_{sel_city}")
        else:
            st.info("표시할 수 있는 좌표가 없습니다. 구글맵 링크를 확인해주세요.")
