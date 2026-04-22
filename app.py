import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

def get_long_url(short_url):
    """짧은 URL을 긴 URL로 변환"""
    try:
        # 주소가 짧은 형식인 경우에만 추적 시도
        if "goo.gl" in short_url or "maps.app.goo.gl" in short_url:
            response = requests.head(short_url, allow_redirects=True, timeout=5)
            return response.url
        return short_url
    except:
        return short_url

def extract_coords(url):
    """URL에서 위도/경도 추출 (짧은 주소 대응)"""
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    
    # 1. 짧은 주소라면 긴 주소로 먼저 변환
    full_url = unquote(get_long_url(url))
    
    try:
        # 패턴 매칭 시작
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
        
        match = re.search(r'([-+]?\d+\.\d+),\s?([-+]?\d+\.\d+)', full_url)
        if match: return float(match.group(1)), float(match.group(2))
    except:
        pass
    return None, None

# --- 이하 데이터 로드 및 UI 로직 (기존과 동일하되 캐시 처리 강화) ---

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=0)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

st.title("💍 2027 유럽 신혼여행 플래너")

if not df.empty:
    st.sidebar.header("📍 여행지 탐색")
    countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
    
    if countries:
        selected_country = st.sidebar.selectbox("1. 국가 선택", countries)
        cities = sorted([c for c in df[df["국가"] == selected_country]["도시"].dropna().unique() if str(c).strip()])
        
        if cities:
            selected_city = st.sidebar.selectbox("2. 도시 선택", cities)
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()

            col_left, col_right = st.columns([1.2, 1.5])

            with col_left:
                st.subheader(f"🗺️ {selected_city} 지도")
                valid_coords = []
                
                # 진행 바 표시 (짧은 URL 변환 시 시간이 걸릴 수 있음)
                with st.spinner('좌표를 분석 중입니다...'):
                    for _, row in filtered_df.iterrows():
                        lat, lon = extract_coords(row.get("구글맵 링크", ""))
                        if lat and lon:
                            valid_coords.append({
                                'lat': lat, 'lon': lon, 
                                'name': row.get('장소명', '장소'), 
                                'priority': row.get('우선순위', 3)
                            })
                
                if valid_coords:
                    avg_lat = sum(c['lat'] for c in valid_coords) / len(valid_coords)
                    avg_lon = sum(c['lon'] for c in valid_coords) / len(valid_coords)
                    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)
                    for c in valid_coords:
                        folium.Marker(
                            [c['lat'], c['lon']],
                            popup=c['name'],
                            tooltip=c['name'],
                            icon=folium.Icon(color="red" if str(c['priority']) == "5" else "blue")
                        ).add_to(m)
                    st_folium(m, width="100%", height=500, key=f"map_{selected_city}")
                else:
                    st.warning("📍 지도에 표시할 좌표를 찾지 못했습니다.")

            with col_right:
                st.subheader("📋 장소 관리")
                edited_df = st.data_editor(filtered_df, use_container_width=True, hide_index=True, num_rows="dynamic")
                if st.button("💾 변경사항 저장", type="primary"):
                    other_df = df[~((df["국가"] == selected_country) & (df["도시"] == selected_city))]
                    final_df = pd.concat([other_df, edited_df], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, data=final_df)
                    st.success("저장 완료!")
                    st.cache_data.clear()
                    st.rerun()

# 추가 폼은 생략 (기존 코드와 동일)
