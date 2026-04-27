import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="플래너", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"
geolocator = Nominatim(user_agent="honeymoon_planner_v20", timeout=10)

# 세션 상태 초기화
if 'search_result' not in st.session_state: st.session_state.search_result = None

# 도시 좌표 사전
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

# 탭 생성 (엑셀의 시트 기능)
tab1, tab2 = st.tabs(["🗺️ 지도 및 체류 개요", "📅 일자별 상세 일정"])

with tab1:
    # 도시 추가 패널
    with st.expander("➕ 새로운 여행지/도시 등록", expanded=False):
        with st.form("add_city"):
            c1, c2, c3, c4 = st.columns(4)
            with c1: add_country = st.text_input("국가")
            with c2: add_city = st.text_input("도시")
            with c3: start_date = st.date_input("시작일")
            with c4: end_date = st.date_input("종료일")
            if st.form_submit_button("등록"):
                lat, lon = KNOWN_CITIES.get(add_city, (None, None))
                if not lat:
                    loc = geolocator.geocode(f"{add_city}, {add_country}")
                    if loc: lat, lon = loc.latitude, loc.longitude
                if lat:
                    new_row = pd.DataFrame([{
                        "국가": add_country, "도시": add_city, "장소명": f"{add_city} 중심",
                        "구글맵 링크": f"https://www.google.com/maps?q={lat},{lon}",
                        "카테고리": "도시", "시작일": start_date, "종료일": end_date
                    }])
                    conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                    st.cache_data.clear()
                    st.rerun()

    # 지도 및 필터
    col_sel, col_edit = st.columns([2, 8])
    with col_sel:
        countries = ["유럽 전체"] + sorted(list(df["국가"].dropna().unique()))
        sel_country = st.selectbox("국가 선택", countries)
        cats = ["도시", "관광지", "맛집", "숙소", "교통시설"]
        sel_cats = [cat for cat in cats if st.checkbox(cat, value=True)]

    with col_edit:
        f_df = df if sel_country == "유럽 전체" else df[df["국가"] == sel_country]
        display_df = f_df[f_df["카테고리"].isin(sel_cats)]
        
        # 지도 렌더링
        valid_points = []
        for _, r in display_df.iterrows():
            lat, lon = extract_coords(r.get("구글맵 링크", ""))
            if lat: valid_points.append({'lat': lat, 'lon': lon, 'name': r['장소명'], 'cat': r['카테고리'], 'country': r['국가']})
        
        c_lat, c_lon = (48.8566, 2.3522) if not valid_points else (sum(p['lat'] for p in valid_points)/len(valid_points), sum(p['lon'] for p in valid_points)/len(valid_points))
        m = folium.Map(location=[c_lat, c_lon], zoom_start=5 if sel_country=="유럽 전체" else 12)
        
        for p in valid_points:
            if p['cat'] == "도시":
                code = get_country_code(p['country'])
                icon = folium.DivIcon(html=f'<img src="https://flagcdn.com/w40/{code}.png" style="width:32px; border-radius:4px;">') if code else folium.DivIcon(html='📍')
            else:
                emoji = {"맛집":"🥄", "숙소":"🏠", "교통시설":"🚆", "관광지":"📸"}.get(p['cat'], "📍")
                icon = folium.DivIcon(html=f'<div style="font-size:24px;">{emoji}</div>')
            folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=icon).add_to(m)
        
        st_folium(m, width="100%", height=600, key="main_map")

        # 체류 기간 요약 표 (한눈에 보기)
        st.subheader("⏱️ 체류 기간 요약")
        summary_df = df[df["카테고리"] == "도시"][["국가", "도시", "시작일", "종료일"]].copy()
        if not summary_df.empty:
            summary_df['시작일'] = pd.to_datetime(summary_df['시작일'])
            summary_df['종료일'] = pd.to_datetime(summary_df['종료일'])
            summary_df['체류일수'] = (summary_df['종료일'] - summary_df['시작일']).dt.days
            st.table(summary_df.sort_values(by='시작일'))

with tab2:
    st.subheader("📅 일자별 상세 일정")
    # 선택된 도시별로 상세 일정 입력
    cities_in_plan = df[df["카테고리"] == "도시"]["도시"].unique()
    selected_city_plan = st.selectbox("상세 일정을 짤 도시를 선택하세요", cities_in_plan)
    
    if selected_city_plan:
        city_info = df[df["도시"] == selected_city_plan].iloc[0]
        st.info(f"📍 {selected_city_plan} 일정 ({city_info['시작일']} ~ {city_info['종료일']})")
        
        # 해당 도시의 상세 일정(관광지, 맛집 등)만 필터링해서 보여줌
        city_details = df[(df["도시"] == selected_city_plan) & (df["카테고리"] != "도시")]
        
        # 일정 추가 폼
        with st.form("add_detail"):
            d1, d2, d3 = st.columns([2, 2, 4])
            with d1: time_input = st.text_input("시간 (예: 10:00)")
            with d2: detail_cat = st.selectbox("종류", ["관광지", "맛집", "숙소", "기타"])
            with d3: detail_name = st.text_input("할 일/장소")
            if st.form_submit_button("상세 일정 추가"):
                new_detail = pd.DataFrame([{
                    "국가": city_info["국가"], "도시": selected_city_plan, "장소명": f"[{time_input}] {detail_name}",
                    "구글맵 링크": "", "카테고리": detail_cat, "메모": "상세일정"
                }])
                conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_detail], ignore_index=True))
                st.cache_data.clear()
                st.rerun()
        
        st.write("---")
        # 저장된 상세 일정 리스트
        if not city_details.empty:
            for _, row in city_details.iterrows():
                st.write(f"- {row['장소명']} ({row['카테고리']})")
        else:
            st.write("아직 등록된 상세 일정이 없습니다.")

st.divider()
# 전체 데이터 편집기 (하단 고정)
with st.expander("📊 전체 데이터 편집 (엑셀 방식)"):
    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic")
    if st.button("모든 변경사항 저장"):
        conn.update(spreadsheet=SHEET_URL, data=edited_df)
        st.cache_data.clear()
        st.rerun()
