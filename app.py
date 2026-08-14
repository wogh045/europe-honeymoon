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

# 한국식 달력 (일요일 시작)
calendar.setfirstweekday(calendar.SUNDAY)

# 1. 페이지 설정
st.set_page_config(page_title="🛫", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

geolocator = Nominatim(user_agent="honeymoon_planner_v35", timeout=10)
geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

# 세션 상태 초기화
if 'search_result' not in st.session_state: st.session_state.search_result = None
if 'last_clicked' not in st.session_state: st.session_state.last_clicked = None
if 'last_country' not in st.session_state: st.session_state.last_country = "유럽 전체 보기"
if 'last_city' not in st.session_state: st.session_state.last_city = "전체 보기"
if 'daily_target_date' not in st.session_state:
    st.session_state.daily_target_date = datetime(2027, 4, 30).date()

KNOWN_CITIES = {
    "로마": (41.9028, 12.4964), "파리": (48.8566, 2.3522), "피렌체": (43.7696, 11.2558),
    "베네치아": (45.4408, 12.3155), "바르셀로나": (41.3851, 2.1734), "런던": (51.5074, -0.1278),
    "프라하": (50.0755, 14.4378), "비엔나": (48.2082, 16.3738), "인터라켄": (46.6863, 7.8632),
    "두바이": (25.2048, 55.2708)
}

# --- 유틸리티 함수 ---
def get_country_code(name):
    name = re.sub(r'\s+', '', str(name).lower())
    mapping = {"이탈리아": "it", "italy": "it", "프랑스": "fr", "france": "fr",
               "스페인": "es", "spain": "es", "스위스": "ch", "switzerland": "ch",
               "영국": "gb", "uk": "gb", "독일": "de", "germany": "de",
               "uae": "ae", "아랍에미리트": "ae", "아랍에미레이트": "ae", "두바이": "ae"}
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
    
    for col in ["시작일", "종료일", "시간", "계획 비용", "실제 일정", "실제 비용", "총 예산"]:
        if col not in df.columns:
            df[col] = "" if col in ["시작일", "종료일", "시간", "실제 일정"] else 0
except Exception as e:
    st.error(f"연결 오류: {e}")
    st.stop()

# --- 메인 UI ---
st.title("🛫")

tab1, tab2, tab3 = st.tabs(["📍 방문 예정지", "📅 체류 일정", "💰 여행 가계부"])

# ==========================================
# [시트 1] 방문 예정지
# ==========================================
with tab1:
    with st.expander("➕ 도시 추가", expanded=False):
        with st.form("add_city", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: add_country = st.text_input("국가", placeholder="예: 스페인")
            with c2: add_city = st.text_input("도시", placeholder="예: 바르셀로나")
            if st.form_submit_button("등록", use_container_width=True):
                if add_country and add_city:
                    lat, lon = KNOWN_CITIES.get(add_city, (None, None))
                    if not lat:
                        try:
                            loc = geocode_with_delay(f"{add_city}, {add_country}")
                            if loc: lat, lon = loc.latitude, loc.longitude
                        except: pass
                    if lat:
                        new_row = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": f"{add_city} 중심", "구글맵 링크": f"https://www.google.com/maps?q={lat},{lon}", "카테고리": "도시", "시작일": "", "종료일": "", "시간": "", "계획 비용": 0, "실제 일정": "", "실제 비용": 0}])
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
            
            initial_zoom = 3 if selected_country == "유럽 전체 보기" else (6 if selected_city == "전체 보기" else 13)
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
                        new_row = pd.DataFrame([{"국가": selected_country if selected_country != "유럽 전체 보기" else "미정", "도시": selected_city if selected_city != "전체 보기" else "미정", "장소명": s_name, "구글맵 링크": f"https://www.google.com/maps?q={target['lat']},{target['lon']}", "카테고리": s_cat, "시작일": "", "종료일": "", "시간": "", "계획 비용": 0, "실제 일정": "", "실제 비용": 0}])
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
# [시트 2] 체류 일정 (투명 버튼 클릭형 원상복구 달력)
# ==========================================
with tab2:
    st.subheader("📅 여행 달력")
    cal_c1, cal_c2, _ = st.columns([1, 1, 8])
    with cal_c1: sel_year = st.selectbox("연도", [2026, 2027, 2028], index=1, key="cal_year")
    with cal_c2: sel_month = st.selectbox("월", list(range(1, 13)), index=3, key="cal_month") # 4월 기본 지정
    st.write("---")
    
    # [핵심] 글자, 이모지가 모두 보이지 않는 "투명 코팅 버튼" CSS 추가
    st.markdown("""
        <style>
        button[title="cal_btn"] {
            height: 90px !important;
            width: 100% !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            color: transparent !important;
            padding: 0 !important;
            margin: 0 !important;
            display: block !important;
            z-index: 10 !important;
        }
        button[title="cal_btn"]:hover {
            background-color: transparent !important;
            border: none !important;
        }
        button[title="cal_btn"] p {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)

    city_df = df[df['카테고리'] == '도시'].copy()
    flag_schedule = {}
    
    for _, row in city_df.iterrows():
        s_date, e_date = str(row.get('시작일', '')).strip(), str(row.get('종료일', '')).strip()
        country_name = row.get('국가', '')
        if s_date and e_date and s_date.lower() not in ['none', 'nat', 'nan'] and e_date.lower() not in ['none', 'nat', 'nan']:
            try:
                start_dt, end_dt = pd.to_datetime(s_date).date(), pd.to_datetime(e_date).date()
                code = get_country_code(country_name)
                # 오리지널 예쁜 국기 이미지
                flag_img = f"<img src='https://flagcdn.com/w40/{code}.png' style='width:32px; border-radius:3px; box-shadow:1px 1px 3px rgba(0,0,0,0.3); margin-top:2px; margin-bottom:2px;'>" if code else "📍"
                curr_dt = start_dt
                while curr_dt <= end_dt:
                    if curr_dt.year == sel_year and curr_dt.month == sel_month:
                        if curr_dt.day in flag_schedule and flag_img not in flag_schedule[curr_dt.day]:
                            flag_schedule[curr_dt.day] += f" {flag_img}"
                        elif curr_dt.day not in flag_schedule:
                            flag_schedule[curr_dt.day] = flag_img
                    curr_dt += timedelta(days=1)
            except: pass 

    # 달력 요일 헤더
    h_cols = st.columns(7)
    days_title = [("일", "red"), ("월", "gray"), ("화", "gray"), ("수", "gray"), ("목", "gray"), ("금", "gray"), ("토", "blue")]
    for idx, (d_name, color) in enumerate(days_title):
        h_cols[idx].markdown(f"<div style='text-align:center; font-weight:bold; font-size:16px; color:{color}; padding-bottom:5px; border-bottom:2px solid #eee;'>{d_name}</div>", unsafe_allow_html=True)
    st.write("")

    cal = calendar.monthcalendar(sel_year, sel_month)
    
    # 달력 본문 렌더링
    for week in cal:
        w_cols = st.columns(7)
        for i, day in enumerate(week):
            with w_cols[i]:
                if day == 0:
                    st.markdown("<div style='height: 90px; background-color: rgba(128,128,128,0.05); border-radius: 8px; margin-bottom: 15px;'></div>", unsafe_allow_html=True)
                else:
                    is_selected = (st.session_state.daily_target_date == datetime(sel_year, sel_month, day).date())
                    
                    # 1. 보이지 않는 투명 버튼으로 사각칸 공간(90px) 확보 및 클릭 신호 캐치
                    if st.button(" ", help="cal_btn", key=f"cal_btn_{sel_year}_{sel_month}_{day}", use_container_width=True):
                        st.session_state.daily_target_date = datetime(sel_year, sel_month, day).date()
                        st.rerun()
                    
                    # 2. 버튼 위를 완벽하게 덮는 시각적 디자인 껍데기 (빨간 테두리 적용)
                    border = "2px solid #ff4b4b" if is_selected else "1px solid rgba(128,128,128,0.2)"
                    day_color = "red" if i == 0 else "blue" if i == 6 else "black"
                    flags = flag_schedule.get(day, "<div style='height:36px;'></div>")
                    
                    # negative margin(-105px)을 주어 투명 버튼 위로 화면을 덮어씌움
                    st.markdown(f"""
                        <div style='
                            margin-top: -106px;
                            height: 90px;
                            border: {border};
                            border-radius: 8px;
                            padding: 5px;
                            text-align: center;
                            pointer-events: none;
                            position: relative;
                            z-index: 5;
                            background-color: white;
                        '>
                            <div style='font-size:16px; font-weight:bold; color:{day_color};'>{day}</div>
                            <div>{flags}</div>
                        </div>
                    """, unsafe_allow_html=True)

    st.write("---")
    
    # ==========================================
    # [일일 상세 일정 네비게이터 & 타임라인]
    # ==========================================
    target_date = st.session_state.daily_target_date
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][target_date.weekday()]
    
    st.markdown(f"<h3 style='text-align:center; margin:0;'>⏱️ {target_date.strftime('%Y년 %m월 %d일')} ({weekday_kr}) 상세 일정</h3>", unsafe_allow_html=True)
    
    nav_c1, nav_c2, nav_c3 = st.columns([1, 8, 1])
    with nav_c1:
        if st.button("◀ 이전 날", use_container_width=True):
            st.session_state.daily_target_date -= timedelta(days=1)
            st.rerun()
    with nav_c3:
        if st.button("다음 날 ▶", use_container_width=True):
            st.session_state.daily_target_date += timedelta(days=1)
            st.rerun()

    overlapping_places = []
    for _, row in df[df['카테고리'] == '도시'].iterrows():
        s_date, e_date = str(row.get('시작일', '')).strip(), str(row.get('종료일', '')).strip()
        if s_date and e_date and s_date.lower() not in ['none', 'nat', 'nan']:
            try:
                s_dt, e_dt = pd.to_datetime(s_date).date(), pd.to_datetime(e_date).date()
                if s_dt <= target_date <= e_dt:
                    overlapping_places.append({'country': row['국가'], 'city': row['도시']})
            except: pass

    current_country, current_city = "", ""
    if overlapping_places:
        header_html = ""
        c_names, city_names = [], []
        
        for i, place in enumerate(overlapping_places):
            cntry, cty = place['country'], place['city']
            code = get_country_code(cntry)
            
            tz_map = {
                "it": "한국 -7시간", "fr": "한국 -7시간", "es": "한국 -7시간", "ch": "한국 -7시간", 
                "de": "한국 -7시간", "at": "한국 -7시간", "cz": "한국 -7시간", "gb": "한국 -8시간", 
                "gr": "한국 -6시간", "ae": "한국 -5시간"
            }
            tz_txt = tz_map.get(code, "")
            
            flag_img = f"<img src='https://flagcdn.com/w40/{code}.png' style='width:36px; border-radius:4px; vertical-align:middle; margin-right:5px;'>" if code else "📍"
            header_html += f"{flag_img} <b>{cntry} {cty}</b> <span style='font-size:14px; color:gray;'>({tz_txt})</span>"
            
            c_names.append(cntry); city_names.append(cty)
            
            if i < len(overlapping_places) - 1:
                header_html += " &nbsp; ✈️ &nbsp; "
        
        st.markdown(f"<div style='text-align:center; margin-top:10px; margin-bottom:15px; background-color:#f0f2f6; padding:10px; border-radius:10px;'>{header_html} 체류 중</div>", unsafe_allow_html=True)
        current_country, current_city = " / ".join(c_names), " / ".join(city_names)
    else:
        st.warning("선택하신 날짜에는 등록된 체류 도시가 없습니다. 아래 [체류 기간 설정]에서 날짜를 지정해보세요.")

    saved_schedule = df[(df['카테고리'] == '일정') & (df['시작일'] == str(target_date))]
    times = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(24) for m in (0, 30)]
    daily_df = pd.DataFrame({
        "시간": times,
        "계획 일정": ["" for _ in range(48)], "계획 지출액": [0 for _ in range(48)],
        "실제 방문": ["" for _ in range(48)], "실제 지출액": [0 for _ in range(48)]
    })
    
    if not saved_schedule.empty:
        for _, r in saved_schedule.iterrows():
            idx = daily_df[daily_df["시간"] == r["시간"]].index
            if not idx.empty:
                plan_str = str(r.get("장소명", ""))
                act_str = str(r.get("실제 일정", ""))
                
                daily_df.loc[idx, "계획 일정"] = "" if plan_str.lower() in ['nan', 'none', 'nat'] else plan_str
                daily_df.loc[idx, "계획 지출액"] = pd.to_numeric(r.get("계획 비용", 0), errors='coerce')
                daily_df.loc[idx, "실제 방문"] = "" if act_str.lower() in ['nan', 'none', 'nat'] else act_str
                daily_df.loc[idx, "실제 지출액"] = pd.to_numeric(r.get("실제 비용", 0), errors='coerce')
                
    daily_df["계획 일정"] = daily_df["계획 일정"].fillna("")
    daily_df["실제 방문"] = daily_df["실제 방문"].fillna("")
    daily_df["계획 지출액"] = daily_df["계획 지출액"].fillna(0)
    daily_df["실제 지출액"] = daily_df["실제 지출액"].fillna(0)

    edited_daily = st.data_editor(
        daily_df,
        use_container_width=True,
        hide_index=True,
        height=480,
        column_config={
            "시간": st.column_config.TextColumn("시간", disabled=True),
            "계획 일정": st.column_config.TextColumn("📝 계획 일정"),
            "계획 지출액": st.column_config.NumberColumn("예상 비용(원)", min_value=0, format="%d ₩"),
            "실제 방문": st.column_config.TextColumn("📸 실제 일정"),
            "실제 지출액": st.column_config.NumberColumn("실제 비용(원)", min_value=0, format="%d ₩")
        },
        key=f"daily_editor_{target_date}"
    )
    
    if st.button("💾 일일 상세 일정 및 비용 저장", type="primary", use_container_width=True, key=f"save_daily_btn_{target_date}"):
        try:
            to_save = edited_daily[(edited_daily["계획 일정"].str.strip() != "") | (edited_daily["계획 지출액"] > 0) | (edited_daily["실제 방문"].str.strip() != "") | (edited_daily["실제 지출액"] > 0)]
            new_main_df = df[~((df["카테고리"] == "일정") & (df["시작일"] == str(target_date)))].copy()
            
            append_list = []
            for _, r in to_save.iterrows():
                p_plan = str(r["계획 일정"]) if pd.notna(r["계획 일정"]) else ""
                p_act = str(r["실제 방문"]) if pd.notna(r["실제 방문"]) else ""
                
                append_list.append({
                    "국가": current_country if current_country else "", "도시": current_city if current_city else "",
                    "장소명": "" if p_plan.lower() in ['nan', 'none'] else p_plan, 
                    "카테고리": "일정", "시작일": str(target_date),
                    "시간": r["시간"], "계획 비용": r["계획 지출액"], 
                    "실제 일정": "" if p_act.lower() in ['nan', 'none'] else p_act, 
                    "실제 비용": r["실제 지출액"],
                    "총 예산": df["총 예산"].max() if "총 예산" in df.columns and not pd.isna(df["총 예산"].max()) else 0
                })
            if append_list: new_main_df = pd.concat([new_main_df, pd.DataFrame(append_list)], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, data=new_main_df)
            st.success(f"{target_date.strftime('%m월 %d일')} 일정이 성공적으로 저장되었습니다!")
            st.cache_data.clear(); st.rerun()
        except Exception as e: st.error("저장에 실패했습니다.")

    st.write("---")
    
    with st.expander("📝 체류 기간 설정 (클릭하여 열기)", expanded=False):
        schedule_editor_df = df[df["카테고리"] == "도시"][["국가", "도시", "시작일", "종료일"]].copy()
        schedule_editor_df["시작일"] = pd.to_datetime(schedule_editor_df["시작일"], errors="coerce").dt.date
        schedule_editor_df["종료일"] = pd.to_datetime(schedule_editor_df["종료일"], errors="coerce").dt.date
        
        edited_schedule = st.data_editor(schedule_editor_df, use_container_width=True, hide_index=True, column_config={"시작일": st.column_config.DateColumn("시작일 (YYYY-MM-DD)"), "종료일": st.column_config.DateColumn("종료일 (YYYY-MM-DD)")})
        if st.button("💾 체류 일정 저장", key="save_schedule_btn"):
            try:
                updated_df = df.copy()
                for idx, row in edited_schedule.iterrows():
                    mask = (updated_df["국가"] == row["국가"]) & (updated_df["도시"] == row["도시"]) & (updated_df["카테고리"] == "도시")
                    s_val, e_val = row["시작일"], row["종료일"]
                    updated_df.loc[mask, "시작일"] = s_val.strftime("%Y-%m-%d") if pd.notnull(s_val) and hasattr(s_val, 'strftime') else ""
                    updated_df.loc[mask, "종료일"] = e_val.strftime("%Y-%m-%d") if pd.notnull(e_val) and hasattr(e_val, 'strftime') else ""
                conn.update(spreadsheet=SHEET_URL, data=updated_df)
                st.cache_data.clear(); st.rerun()
            except Exception as e: st.error("저장 실패.")

# ==========================================
# [시트 3] 여행 가계부
# ==========================================
with tab3:
    st.subheader("💰 전체 여행 가계부")
    current_budget = 0
    if not df.empty and "총 예산" in df.columns:
        loaded_budget = pd.to_numeric(df["총 예산"], errors='coerce').max()
        if pd.notna(loaded_budget): current_budget = int(loaded_budget)
        
    with st.form("budget_form"):
        new_budget = st.number_input("총 여행 예산 입력 (원)", min_value=0, step=100000, value=current_budget)
        if st.form_submit_button("예산 저장", type="primary"):
            if not df.empty:
                df["총 예산"] = new_budget
                conn.update(spreadsheet=SHEET_URL, data=df)
                st.success("총 예산이 업데이트되었습니다!")
                st.cache_data.clear(); st.rerun()

    st.write("---")
    schedule_rows = df[df["카테고리"] == "일정"]
    total_planned_cost = pd.to_numeric(schedule_rows["계획 비용"], errors='coerce').sum()
    total_actual_cost = pd.to_numeric(schedule_rows["실제 비용"], errors='coerce').sum()
    
    remain_planned = current_budget - total_planned_cost
    remain_actual = current_budget - total_actual_cost
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.markdown("### 📝 계획 예산 현황")
        st.metric(label="계획 지출 총액", value=f"{total_planned_cost:,.0f} 원")
        if remain_planned < 0: st.error(f"🚨 예산 초과! ( {-remain_planned:,.0f} 원 부족 )")
        else: st.success(f"✅ 남은 계획 예산: {remain_planned:,.0f} 원")

    with col_b2:
        st.markdown("### 📸 실제 지출 현황")
        st.metric(label="실제 사용 총액", value=f"{total_actual_cost:,.0f} 원")
        if remain_actual < 0: st.error(f"🚨 실제 예산 초과! ( {-remain_actual:,.0f} 원 빚짐 )")
        else: st.info(f"💵 여행 중 남은 돈: {remain_actual:,.0f} 원")
