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

# [수정 1] 새로운 여행지 추가하기를 최상단에 배치
with st.expander("➕ 새로운 여행지 추가하기", expanded=False):
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: add_country = st.text_input("국가")
        with c2: add_city = st.text_input("도시")
        with c3: add_place = st.text_input("장소명")
        
        c4, c5 = st.columns([3, 1])
        with c4: add_url = st.text_input("구글맵 링크 (짧은 주소 가능)")
        with c5: add_priority = st.selectbox("우선순위", [1, 2, 3, 4, 5], index=2)
        
        if st.form_submit_button("시트에 저장하기", use_container_width=True):
            if add_country and add_city and add_place:
                new_row = pd.DataFrame([{
                    "국가": add_country, "도시": add_city, "장소명": add_place, 
                    "구글맵 링크": add_url, "우선순위": add_priority
                }])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=updated_df)
                st.success(f"'{add_place}' 추가 완료!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("국가, 도시, 장소명은 필수입니다.")

st.divider()

# [수정 2] 여행지 선택(좌) 및 장소 관리(우) 배치
if not df.empty:
    main_col_left, main_col_right = st.columns([1, 3]) # 왼쪽 선택창을 1, 오른쪽 관리창을 3 비율로 설정

    with main_col_left:
        st.subheader("📍 여행지 선택")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        if countries:
            # 상하로 배치된 국가/도시 선택창
            selected_country = st.selectbox("1. 국가 선택", countries)
            
            city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
            cities = sorted([c for c in city_list if str(c).strip()])
            
            if cities:
                selected_city = st.selectbox("2. 도시 선택", cities)
                filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            else:
                st.info("등록된 도시가 없습니다.")
                filtered_df = pd.DataFrame()
        else:
            st.info("등록된 국가가 없습니다.")
            filtered_df = pd.DataFrame()

    with main_col_right:
        st.subheader("📋 장소 관리")
        if not filtered_df.empty:
            edited_df = st.data_editor(
                filtered_df, 
                use_container_width=True, 
                hide_index=True, 
                num_rows="dynamic"
            )
            
            if st.button("💾 변경사항 시트에 저장", type="primary", use_container_width=True):
                other_df = df[~((df["국가"] == selected_country) & (df["도시"] == selected_city))]
                final_df = pd.concat([other_df, edited_df], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=final_df)
                st.success("시트 업데이트 완료!")
                st.cache_data.clear()
                st.rerun()
        else:
            st.write("왼쪽에서 도시를 선택하면 장소 목록이 나타납니다.")

    # 하단 지도 영역 (선택된 도시가 있을 때만 표시)
    if not filtered_df.empty:
        st.divider()
        st.subheader(f"🗺️ {selected_city} 여행 지도")
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
            st.info("지도를 표시할 수 있는 구글맵 링크가 없습니다.")
