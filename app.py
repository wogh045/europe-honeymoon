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

# [1] 새로운 여행지 추가하기 섹션 (최상단)
with st.expander("➕ 새로운 여행지 추가하기", expanded=False):
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: add_country = st.text_input("국가", placeholder="예: 이탈리아")
        with c2: add_city = st.text_input("도시", placeholder="예: 로마")
        with c3: add_place = st.text_input("장소명", placeholder="예: 콜로세움")
        
        c4, c5 = st.columns([3, 1])
        with c4: add_url = st.text_input("구글맵 링크", placeholder="짧은 주소도 가능합니다")
        with c5: add_category = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
        
        if st.form_submit_button("시트에 저장하기", use_container_width=True):
            if add_country and add_city and add_place:
                new_row = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": add_place, "구글맵 링크": add_url, "카테고리": add_category}])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=updated_df)
                st.success(f"'{add_place}' 추가 완료!")
                st.cache_data.clear()
                st.rerun()

st.divider()

# [2] 여행지 선택 및 관리 섹션
if not df.empty:
    main_col_left, main_col_right = st.columns([1, 3])

    with main_col_left:
        st.subheader("📍 여행지 탐색")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        
        selected_country = st.selectbox("1. 국가 선택", countries)
        
        # 도시 목록에 '전체 보기' 옵션 추가
        city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
        cities = ["전체 보기"] + sorted([c for c in city_list if str(c).strip()])
        selected_city = st.selectbox("2. 도시 선택", cities)
        
        st.write("---")
        # [업그레이드] 카테고리 필터 체크박스
        st.markdown("**🔍 카테고리 필터**")
        all_categories = ["관광지", "맛집", "숙소", "교통시설", "기타"]
        selected_categories = []
        for cat in all_categories:
            if st.checkbox(cat, value=True):
                selected_categories.append(cat)

    with main_col_right:
        # 데이터 필터링 로직
        if selected_city == "전체 보기":
            filtered_df = df[df["국가"] == selected_country].copy()
            title_text = f"🗺️ {selected_country} 전체 지도"
        else:
            filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()
            title_text = f"🗺️ {selected_city} 지도"
        
        # 카테고리 필터 적용
        display_df = filtered_df[filtered_df["카테고리"].isin(selected_categories)].copy()

        # 지도 표시 영역
        st.subheader(title_text)
        valid_coords = []
        with st.spinner('좌표 분석 중...'):
            for _, row in display_df.iterrows():
                lat, lon = extract_coords(row.get("구글맵 링크", ""))
                if lat and lon:
                    valid_coords.append({
                        'lat': lat, 'lon': lon, 
                        'name': row.get('장소명', '장소'),
                        'cat': row.get('카테고리', '기타'),
                        'city': row.get('도시', '')
                    })
        
        if valid_coords:
            avg_lat = sum(c['lat'] for c in valid_coords) / len(valid_coords)
            avg_lon = sum(c['lon'] for c in valid_coords) / len(valid_coords)
            
            # 전체 보기일 때는 줌 레벨을 낮춰서 넓게 보이게 설정
            zoom = 6 if selected_city == "전체 보기" else 13
            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom)
            
            for c in valid_coords:
                color = "red" if c['cat'] == "관광지" else "orange" if c['cat'] == "맛집" else "green" if c['cat'] == "숙소" else "purple" if c['cat'] == "교통시설" else "blue"
                folium.Marker(
                    [c['lat'], c['lon']],
                    popup=f"({c['city']}) {c['name']}",
                    tooltip=f"[{c['cat']}] {c['name']}",
                    icon=folium.Icon(color=color, icon='info-sign')
                ).add_to(m)
            st_folium(m, width="100%", height=500, key=f"map_{selected_country}_{selected_city}")
        else:
            st.info("표시할 장소가 없습니다. 필터를 확인하거나 구글맵 링크를 등록해주세요.")

        st.divider()
        st.subheader("📋 장소 데이터 관리")
        edited_df = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
        
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True):
            # 필터링되지 않은 나머지 데이터와 합쳐서 저장
            other_data = df[~df.index.isin(display_df.index)]
            final_df = pd.concat([other_data, edited_df], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, data=final_df)
            st.success("저장되었습니다!")
            st.cache_data.clear()
            st.rerun()
