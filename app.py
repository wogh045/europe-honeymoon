import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection

# 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

# 시트 URL (본인의 시트 URL로 확인 필수)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1BVAUJ05mVkzgi2dprZ1w60b34YifUlZGxnVehPzO4aE/edit"

def extract_coords(url):
    """구글맵 URL에서 위도/경도 추출"""
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    try:
        url = unquote(url)
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url)
        if match: return float(match.group(1)), float(match.group(2))
    except:
        pass
    return None, None

# 1. 메인 연결부 (에러 처리 강화)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL)
    df.columns = df.columns.str.strip()
except Exception as e:
    st.error("⚠️ 구글 시트에 연결할 수 없습니다. Secrets 설정이나 시트 공유를 확인해주세요.")
    st.stop() # 연결 안되면 여기서 중단

st.title("💍 2027 유럽 신혼여행 플래너")

# 2. 데이터가 아예 없는 경우 처리
if df.empty:
    st.info("시트에 데이터가 없습니다. 아래 '새로운 여행지 추가하기'를 통해 첫 장소를 등록해보세요!")
    # 데이터가 없어도 추가 폼은 보여줌
else:
    # 탐색 및 관리 섹션
    st.sidebar.header("📍 여행지 탐색")
    countries = sorted([c for c in df["국가"].dropna().unique() if c])
    
    if not countries:
        st.info("국가 정보가 없습니다. 데이터를 먼저 입력해주세요.")
    else:
        selected_country = st.sidebar.selectbox("1. 국가 선택", countries)
        city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
        cities = sorted([c for c in city_list if c])
        
        if not cities:
            st.info("해당 국가에 등록된 도시가 없습니다.")
        else:
            selected_city = st.sidebar.selectbox("2. 도시 선택", cities)
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()

            col_left, col_right = st.columns([1.2, 1.5])

            with col_left:
                st.subheader(f"🗺️ {selected_city} 지도")
                
                # 좌표 추출 로직 (안정성 강화)
                map_df = filtered_df.copy()
                valid_coords = []
                
                for idx, row in map_df.iterrows():
                    lat, lon = extract_coords(row.get("구글맵 링크", ""))
                    if lat and lon:
                        valid_coords.append({'lat': lat, 'lon': lon, 'name': row.get('장소명', '알 수 없음'), 'priority': row.get('우선순위', 3)})
                
                if valid_coords:
                    # 지도 생성
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
                    st.warning("📍 이 도시에는 구글맵 링크가 등록된 장소가 없어 지도를 표시할 수 없습니다.")

            with col_right:
                st.subheader("📋 데이터 관리")
                edited_df = st.data_editor(filtered_df, num_rows="dynamic", use_container_width=True, hide_index=True)
                if st.button("💾 변경사항 저장", type="primary"):
                    final_df = df[~((df["국가"] == selected_country) & (df["도시"] == selected_city))]
                    final_df = pd.concat([final_df, edited_df], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, data=final_df)
                    st.success("저장되었습니다!")
                    st.cache_data.clear()
                    st.rerun()

st.divider()

# 3. 추가 섹션 (하단 배치)
with st.expander("➕ 새로운 여행지 추가하기"):
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: new_country = st.text_input("국가")
        with c2: new_city = st.text_input("도시")
        with c3: new_place = st.text_input("장소명")
        new_url = st.text_input("구글맵 링크 (좌표 추출용)")
        if st.form_submit_button("시트에 추가"):
            if new_country and new_city and new_place:
                new_row = pd.DataFrame([{"국가": new_country, "도시": new_city, "장소명": new_place, "구글맵 링크": new_url, "우선순위": 3}])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=updated_df)
                st.success("추가되었습니다!")
                st.cache_data.clear()
                st.rerun()
