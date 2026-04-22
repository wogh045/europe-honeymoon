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

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

def get_long_url(short_url):
    try:
        if "goo.gl" in short_url or "maps.app.goo.gl" in short_url:
            response = requests.head(short_url, allow_redirects=True, timeout=5)
            return response.url
        return short_url
    except:
        return short_url

def extract_coords(url):
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

# 데이터 연결
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=0)
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

# --- UI 시작 ---
st.title("💍 2027 유럽 신혼여행 플래너")

if not df.empty:
    # [변경 사항] 여행지 탐색 섹션을 가로로 배치
    st.markdown("### 📍 여행지 선택")
    filter_col1, filter_col2 = st.columns(2)
    
    countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
    
    if countries:
        with filter_col1:
            selected_country = st.selectbox("1. 국가를 선택하세요", countries, label_visibility="collapsed")
        
        city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
        cities = sorted([c for c in city_list if str(c).strip()])
        
        if cities:
            with filter_col2:
                selected_city = st.selectbox("2. 도시를 선택하세요", cities, label_visibility="collapsed")
            
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            
            st.divider()

            # 지도와 표 배치
            col_left, col_right = st.columns([1.2, 1.5])

            with col_left:
                st.subheader(f"🗺️ {selected_city} 지도")
                valid_coords = []
                with st.spinner('좌표 분석 중...'):
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
                    st.warning("📍 표시할 좌표가 없습니다.")

            with col_right:
                st.subheader("📋 장소 관리")
                edited_df = st.data_editor(
                    filtered_df, 
                    use_container_width=True, 
                    hide_index=True, 
                    num_rows="dynamic"
                )
                
                if st.button("💾 이 도시 정보 저장", type="primary", use_container_width=True):
                    other_df = df[~((df["국가"] == selected_country) & (df["도시"] == selected_city))]
                    final_df = pd.concat([other_df, edited_df], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, data=final_df)
                    st.success("저장 완료!")
                    st.cache_data.clear()
                    st.rerun()

st.divider()

# 새로운 장소 추가 (기존과 동일하게 유지하되 하단에 배치)
with st.expander("➕ 새로운 여행지 추가하기"):
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: add_country = st.text_input("국가")
        with c2: add_city = st.text_input("도시")
        with c3: add_place = st.text_input("장소명")
        add_url = st.text_input("구글맵 링크")
        if st.form_submit_button("시트에 저장"):
            if add_country and add_city and add_place:
                new_data = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": add_place, "구글맵 링크": add_url, "우선순위": 3}])
                updated_all = pd.concat([df, new_data], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=updated_all)
                st.success("추가되었습니다!")
                st.cache_data.clear()
                st.rerun()
