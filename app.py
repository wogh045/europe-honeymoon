import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
import requests
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderRateLimited
from geopy.extra.rate_limiter import RateLimiter
import calendar
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="플래너", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

geolocator = Nominatim(user_agent="honeymoon_planner_v22", timeout=10)
geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

# 세션 상태 초기화
if 'search_result' not in st.session_state: st.session_state.search_result = None
if 'last_clicked' not in st.session_state: st.session_state.last_clicked = None
if 'last_country' not in st.session_state: st.session_state.last_country = "유럽 전체 보기"
if 'last_city' not in st.session_state: st.session_state.last_city = "전체 보기"

KNOWN_CITIES = {
    "로마": (41.9028, 12.4964), "파리": (48.8566, 2.3522), "피렌체": (43.7696, 11.2558),
    "베네치아": (45.4408, 12.3155), "바르셀로나": (41.3851, 2.1734), "런던": (51.5074, -0.1278),
    "프라하": (50.0755, 14.4378), "비엔나": (48.2082, 16.3738), "인터라켄": (46.6863, 7.8632)
}

# --- 유틸리티 함수 ---
def get_country_code(name):
    name = re.sub(r'\s+', '', str(name).lower())
    mapping = {"이탈리아": "it", "italy": "it", "프랑스": "fr", "france": "fr",
               "스페인": "es", "spain": "es", "스위스": "ch", "switzerland": "ch",
               "영국": "gb", "uk": "gb", "독일": "de", "germany": "de"}
    return mapping.get(name, "")

def extract_coords(url):
    if not url or pd.isna(url): return None, None
    try:
        url_str = unquote(str(url))
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
        match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# --- 데이터 로드 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    df.columns = [str(c).strip() for c in df.columns]
    for col in ["시작일", "종료일"]:
        if col not in df.columns:
            df[col] = None
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

# --- 메인 UI: 플래너 ---
st.title("💍 플래너")

tab1, tab2 = st.tabs(["📍 방문 예정지", "📅 체류 일정"])

# ==========================================
# [시트 1] 방문 예정지 (지도 & 장소 관리)
# ==========================================
with tab1:
    with st.expander("➕ 도시 추가", expanded=False):
        with st.form("add_city", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: add_country = st.text_input("국가")
            with c2: add_city = st.text_input("도시")
            if st.form_submit_button("등록", use_container_width=True):
                if add_country and add_city:
                    lat, lon = KNOWN_CITIES.get(add_city, (None, None))
                    if not lat:
                        try:
                            loc = geocode_with_delay(f"{add_city}, {add_country}")
                            if loc: lat, lon = loc.latitude, loc.longitude
                        except: pass
                    if lat:
                        new_row = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": f"{add_city} 중심", "구글맵 링크": f"https://www.google.com/maps?q={lat},{lon}", "카테고리": "도시", "시작일": "", "종료일": ""}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.cache_data.clear()
                        st.rerun()

    if not df.empty:
        col_sel, col_edit = st.columns([2, 8])
        with col_sel:
            countries = ["유럽 전체 보기"] + sorted(list(df["국가"].dropna().unique()))
            selected_country = st.selectbox("국가 선택", countries)
            if selected_country != st.session_state.last_country:
                st.session_state.search_result = st.session_state.last_clicked = None
                st.session_state.last_country = selected_country
            
            city_list = df[df["국가"] == selected_country]["도시"].unique() if selected_country != "유럽 전체 보기" else []
            selected_city = st.selectbox("도시 선택", ["전체 보기"] + list(city_list)) if selected_country != "유럽 전체 보기" else "전체 보기"
            
            st.write("---")
            cats = ["도시", "관광지", "맛집", "숙소", "교통시설"]
            selected_cats = [cat for cat in cats if st.checkbox(cat, value=True)]

        with col_edit:
            search_q = st.text_input("🔍", placeholder="장소 검색")
            if search_q:
                try:
                    loc = geocode_with_delay(search_q)
                    if loc:
                        st.session_state.search_result = {'lat': loc.latitude, 'lon': loc.longitude, 'name': search_q}
                        st.session_state.last_clicked = None
                    else: st.warning("장소를 찾을 수 없습니다.")
                except GeocoderRateLimited: st.error("잠시 후 다시 검색해주세요.")

            f_df = df if selected_country == "유럽 전체 보기" else df[df["국가"] == selected_country]
            if selected_city != "전체 보기": f_df = f_df[f_df["도시"] == selected_city]
            display_df = f_df[f_df["카테고리"].isin(selected_cats)]
            
            valid_points = []
            for _, r in display_df.iterrows():
                lat, lon = extract_coords(r.get("구글맵 링크", ""))
                if lat: valid_points.append({'lat': lat, 'lon': lon, 'name': r['장소명'], 'cat': r['카테고리'], 'country': r['국가'], 'city': r['도시']})
            
            initial_zoom = 4 if selected_country == "유럽 전체 보기" else (6 if selected_city == "전체 보기" else 13)
            if st.session_state.last_clicked: c_lat, c_lon = st.session_state.last_clicked['lat'], st.session_state.last_clicked['lng']
            elif st.session_state.search_result: c_lat, c_lon = st.session_state.search_result['lat'], st.session_state.search_result['lon']; initial_zoom = 16
            elif valid_points: c_lat, c_lon = sum(p['lat'] for p in valid_points)/len(valid_points), sum(p['lon'] for p in valid_points)/len(valid_points)
            else: c_lat, c_lon = 48.8566, 2.3522

            m = folium.Map(location=[c_lat, c_lon], zoom_start=initial_zoom)
            is_detailed = initial_zoom >= 10

            for p in valid_points:
                if p['cat'] == "도시":
                    if not is_detailed:
                        code = get_country_code(p['country'])
                        icon = folium.DivIcon(html=f'<img src="https://flagcdn.com/w40/{code}.png" style="width:34px; border-radius:4px; box-shadow:2px 2px 5px rgba(0,0,0,0.3);">') if code else folium.DivIcon(html='📍')
                        folium.Marker([p['lat'], p['lon']], tooltip=p['city'], icon=icon).add_to(m)
                else:
                    if is_detailed:
                        emj = {"맛집":"🥄", "숙소":"🏠", "교통시설":"🚆", "관광지":"📸"}.get(p['cat'], "📍")
                        icon = folium.DivIcon(html=f'<div style="font-size:32px; text-shadow: -2px 0 white, 0 2px white, 2px 0 white, 0 -2px white;">{emj}</div>')
                        folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=icon).add_to(m)
            
            if st.session_state.search_result: folium.Marker([st.session_state.search_result['lat'], st.session_state.search_result['lon']], icon=folium.DivIcon(html='<div style="font-size:40px;">📍</div>')).add_to(m)
            if st.session_state.last_clicked: folium.Marker([st.session_state.last_clicked['lat'], st.session_state.last_clicked['lng']], icon=folium.DivIcon(html='<div style="font-size:40px;">🎯</div>')).add_to(m)

            map_out = st_folium(m, width="100%", height=750, key=f"map_{selected_country}_{selected_city}")
            if map_out and map_out.get('last_clicked'):
                if st.session_state.last_clicked != map_out['last_clicked']:
                    st.session_state.last_clicked = map_out['last_clicked']; st.session_state.search_result = None; st.rerun()

            target = st.session_state.search_result or (st.session_state.last_clicked and {'lat':st.session_state.last_clicked['lat'], 'lon':st.session_state.last_clicked['lng'], 'name':'수동 선택 장소'})
            if target:
                with st.form("save_place"):
                    st.write(f"💾 {target.get('name', '장소')} 저장")
                    s_name = st.text_input("이름", value=target.get('name', ''))
                    s_cat = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통시설", "기타"])
                    if st.form_submit_button("저장"):
                        new_row = pd.DataFrame([{"국가": selected_country if selected_country != "유럽 전체 보기" else "미정", "도시": selected_city if selected_city != "전체 보기" else "미정", "장소명": s_name, "구글맵 링크": f"https://www.google.com/maps?q={target['lat']},{target['lon']}", "카테고리": s_cat, "시작일": "", "종료일": ""}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.session_state.search_result = st.session_state.last_clicked = None; st.cache_data.clear(); st.rerun()

            st.divider()
            st.subheader("📋")
            edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
            if st.button("💾 시트 변경사항 저장", key="save_btn_1"):
                other = df[~df.index.isin(display_df.index)]
                conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
                st.cache_data.clear(); st.rerun()

# ==========================================
# [시트 2] 체류 일정 (달력 뷰)
# ==========================================
with tab2:
    st.subheader("📅 여행 달력")
    
    cal_c1, cal_c2, _ = st.columns([1, 1, 8])
    with cal_c1: sel_year = st.selectbox("연도", [2026, 2027, 2028], index=1)
    with cal_c2: sel_month = st.selectbox("월", list(range(1, 13)), index=4)
        
    st.write("---")
    
    city_df = df[df['카테고리'] == '도시'].copy()
    flag_schedule = {}
    
    for _, row in city_df.iterrows():
        s_date = str(row.get('시작일', '')).strip()
        e_date = str(row.get('종료일', '')).strip()
        country_name = row.get('국가', '')
        
        if s_date and e_date and s_date.lower() != 'none' and e_date.lower() != 'none':
            try:
                start_dt = pd.to_datetime(s_date).date()
                end_dt = pd.to_datetime(e_date).date()
                code = get_country_code(country_name)
                
                flag_img = f"<img src='https://flagcdn.com/w40/{code}.png' style='width:30px; border-radius:3px; box-shadow:1px 1px 3px rgba(0,0,0,0.3); margin-top:5px;'>" if code else "📍"
                
                curr_dt = start_dt
                while curr_dt <= end_dt:
                    if curr_dt.year == sel_year and curr_dt.month == sel_month:
                        # 같은 날 여러 도시가 겹칠 경우 국기를 옆으로 나열
                        if curr_dt.day in flag_schedule and flag_img not in flag_schedule[curr_dt.day]:
                            flag_schedule[curr_dt.day] += f" {flag_img}"
                        else:
                            flag_schedule[curr_dt.day] = flag_img
                    curr_dt += timedelta(days=1)
            except: pass 

    cal = calendar.monthcalendar(sel_year, sel_month)
    
    html_cal = f"""
    <style>
        .planner-cal {{ width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; }}
        .planner-cal th {{ background-color: rgba(128,128,128,0.1); padding: 10px; border: 1px solid rgba(128,128,128,0.2); text-align: center; font-weight: bold; }}
        .planner-cal td {{ border: 1px solid rgba(128,128,128,0.2); height: 100px; vertical-align: top; padding: 5px; text-align: center; }}
        .cal-day-num {{ font-size: 16px; font-weight: bold; color: gray; }}
        .cal-empty {{ background-color: rgba(128,128,128,0.05); }}
    </style>
    <table class="planner-cal">
        <tr><th style='color:red;'>일</th><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th><th style='color:blue;'>토</th></tr>
    """
    
    for week in cal:
        html_cal += "<tr>"
        for i, day in enumerate(week):
            if day == 0:
                html_cal += "<td class='cal-empty'></td>"
            else:
                day_color = "red" if i == 0 else "blue" if i == 6 else "inherit"
                flag = flag_schedule.get(day, "")
                html_cal += f"<td><div class='cal-day-num' style='color:{day_color};'>{day}</div>{flag}</td>"
        html_cal += "</tr>"
    html_cal += "</table>"
    
    st.markdown(html_cal, unsafe_allow_html=True)
    st.write("---")
    
    st.subheader("📝 체류 기간 설정")
    st.info("아래 표의 '시작일'과 '종료일'을 더블클릭하여 여행 기간을 입력하세요. 달력 위젯 충돌 오류가 해결되었습니다!")
    
    schedule_editor_df = df[df["카테고리"] == "도시"][["국가", "도시", "시작일", "종료일"]].copy()
    
    # [핵심 수정] 글자나 빈칸으로 되어있던 데이터를 안전한 '날짜(Datetime) 객체'로 강제 변환
    schedule_editor_df["시작일"] = pd.to_datetime(schedule_editor_df["시작일"], errors="coerce").dt.date
    schedule_editor_df["종료일"] = pd.to_datetime(schedule_editor_df["종료일"], errors="coerce").dt.date
    
    edited_schedule = st.data_editor(
        schedule_editor_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "시작일": st.column_config.DateColumn("시작일 (YYYY-MM-DD)", format="YYYY-MM-DD"),
            "종료일": st.column_config.DateColumn("종료일 (YYYY-MM-DD)", format="YYYY-MM-DD")
        }
    )
    
    if st.button("💾 일정 저장", key="save_schedule_btn", type="primary"):
        try:
            updated_df = df.copy()
            for idx, row in edited_schedule.iterrows():
                mask = (updated_df["국가"] == row["국가"]) & (updated_df["도시"] == row["도시"]) & (updated_df["카테고리"] == "도시")
                updated_df.loc[mask, "시작일"] = str(row["시작일"]) if pd.notna(row["시작일"]) else ""
                updated_df.loc[mask, "종료일"] = str(row["종료일"]) if pd.notna(row["종료일"]) else ""
            
            conn.update(spreadsheet=SHEET_URL, data=updated_df)
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error("저장에 실패했습니다. 1분 후 다시 시도해주세요.")
