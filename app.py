import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection

# 1. 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

# 2. 바뀐 구글 시트 URL 적용
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

def extract_coords(url):
    """구글맵 URL에서 위도/경도를 더 정확하게 추출"""
    if not url or pd.isna(url) or not isinstance(url, str): return None, None
    try:
        url = unquote(url)
        # 패턴 1: @위도,경도 (일반적인 주소창 주소)
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url)
        if match: return float(match.group(1)), float(match.group(2))
        
        # 패턴 2: !3d위도!4d경도 (검색 결과 URL)
        match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url)
        if match: return float(match.group(1)), float(match.group(2))
        
        # 패턴 3: 숫자,숫자 형태 (단순 위경도 입력 시)
        match = re.search(r'([-+]?\d+\.\d+),\s?([-+]?\d+\.\d+)', url)
        if match: return float(match.group(1)), float(match.group(2))
    except:
        pass
    return None, None

# 3. 데이터 연결 및 로드
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # TTL을 0으로 설정하여 항상 최신 데이터를 가져오도록 함
    df = conn.read(spreadsheet=SHEET_URL, ttl=0)
    
    # [중요] 컬럼명 정리: 앞뒤 공백 제거 및 문자열 변환
    df.columns = [str(c).strip() for c in df.columns]
except Exception as e:
    st.error(f"❌ 시트 연결 오류: {e}")
    st.info("💡 Secrets 설정과 시트 공유(편집자 권한)를 다시 한번 확인해주세요.")
    st.stop()

st.title("💍 2027 유럽 신혼여행 플래너")
st.caption(f"연결된 시트: {SHEET_URL}")

# 4. 앱 로직 시작
if not df.empty:
    # 필수 컬럼 체크
    required_cols = ["국가", "도시", "장소명", "구글맵 링크"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    
    if missing_cols:
        st.warning(f"⚠️ 시트에 '{', '.join(missing_cols)}' 열이 보이지 않습니다. 열 이름을 확인해주세요.")
        st.write("현재 시트 열 이름:", list(df.columns))
    else:
        # 사이드바 탐색
        st.sidebar.header("📍 여행지 검색")
        countries = sorted([c for c in df["국가"].dropna().unique() if str(c).strip()])
        
        if countries:
            selected_country = st.sidebar.selectbox("1. 국가 선택", countries)
            city_list = df[df["국가"] == selected_country]["도시"].dropna().unique()
            cities = sorted([c for c in city_list if str(c).strip()])
            
            if cities:
                selected_city = st.sidebar.selectbox("2. 도시 선택", cities)
                filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()

                col_left, col_right = st.columns([1.2, 1.5])

                with col_left:
                    st.subheader(f"🗺️ {selected_city} 지도")
                    valid_coords = []
                    for _, row in filtered_df.iterrows():
                        lat, lon = extract_coords(row.get("구글맵 링크", ""))
                        if lat and lon:
                            valid_coords.append({
                                'lat': lat, 'lon': lon, 
                                'name': row.get('장소명', '장소'), 
                                'priority': row.get('우선순위', 3),
                                'category': row.get('카테고리', '기타')
                            })
                    
                    if valid_coords:
                        avg_lat = sum(c['lat'] for c in valid_coords) / len(valid_coords)
                        avg_lon = sum(c['lon'] for c in valid_coords) / len(valid_coords)
                        
                        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)
                        for c in valid_coords:
                            # 우선순위가 5이면 빨간색, 나머지는 파란색 마커
                            color = "red" if str(c['priority']) == "5" else "blue"
                            folium.Marker(
                                [c['lat'], c['lon']],
                                popup=f"<b>{c['name']}</b><br>{c['category']}",
                                tooltip=c['name'],
                                icon=folium.Icon(color=color, icon='info-sign')
                            ).add_to(m)
                        st_folium(m, width="100%", height=500, key=f"map_{selected_city}")
                    else:
                        st.warning("📍 지도를 표시할 수 없습니다.")
                        st.info("💡 원인: 구글맵 링크에서 좌표(@위도,경도)를 찾을 수 없습니다. 주소창의 전체 URL을 복사해서 넣어주세요.")

                with col_right:
                    st.subheader("📋 장소 리스트")
                    # 데이터 에디터 (수정 기능)
                    edited_df = st.data_editor(
                        filtered_df, 
                        use_container_width=True, 
                        hide_index=True,
                        num_rows="dynamic"
                    )
                    
                    if st.button("💾 이 도시의 변경사항 저장", type="primary"):
                        # 해당 도시 외 데이터 + 수정한 데이터 합치기
                        other_df = df[~((df["국가"] == selected_country) & (df["도시"] == selected_city))]
                        final_df = pd.concat([other_df, edited_df], ignore_index=True)
                        conn.update(spreadsheet=SHEET_URL, data=final_df)
                        st.success("시트에 성공적으로 저장되었습니다!")
                        st.cache_data.clear()
                        st.rerun()

st.divider()

# 5. 새로운 여행지 추가 섹션
with st.expander("➕ 새로운 여행지 추가하기"):
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: add_country = st.text_input("국가", placeholder="예: 프랑스")
        with c2: add_city = st.text_input("도시", placeholder="예: 파리")
        with c3: add_place = st.text_input("장소명", placeholder="예: 에펠탑")
        
        c4, c5 = st.columns([2, 1])
        with c4: add_url = st.text_input("구글맵 링크", placeholder="주소창의 긴 URL을 붙여넣으세요")
        with c5: add_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "기타"])
        
        if st.form_submit_button("시트에 영구 추가"):
            if add_country and add_city and add_place:
                new_data = pd.DataFrame([{
                    "국가": add_country, "도시": add_city, "장소명": add_place,
                    "구글맵 링크": add_url, "카테고리": add_cat, "우선순위": 3
                }])
                updated_all = pd.concat([df, new_data], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, data=updated_all)
                st.success(f"{add_place} 장소가 추가되었습니다!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("국가, 도시, 장소명은 필수입니다.")
