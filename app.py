import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import calendar
from datetime import datetime, timedelta

# 한국식 달력 (일요일 시작)
calendar.setfirstweekday(calendar.SUNDAY)

# 1. 페이지 설정
st.set_page_config(page_title="🛫", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jUe_li1kObxdCQ_Xp62AlOOFEzTCcG48srKqam8hTc4/edit"

# --- 지오코더 설정 및 캐싱 ---
geolocator = Nominatim(user_agent="honeymoon_planner_v40", timeout=10)
geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_location(query):
    try:
        loc = geocode_with_delay(query)
        if loc:
            return {'lat': loc.latitude, 'lon': loc.longitude, 'name': query}
    except:
        pass
    return None

# --- 국가 정보 딕셔너리 ---
COUNTRY_INFO = {
    "이탈리아": {"code": "it", "tz": "한국 -7시간"}, "italy": {"code": "it", "tz": "한국 -7시간"},
    "프랑스": {"code": "fr", "tz": "한국 -7시간"}, "france": {"code": "fr", "tz": "한국 -7시간"},
    "스페인": {"code": "es", "tz": "한국 -7시간"}, "spain": {"code": "es", "tz": "한국 -7시간"},
    "스위스": {"code": "ch", "tz": "한국 -7시간"}, "switzerland": {"code": "ch", "tz": "한국 -7시간"},
    "영국": {"code": "gb", "tz": "한국 -8시간"}, "uk": {"code": "gb", "tz": "한국 -8시간"},
    "독일": {"code": "de", "tz": "한국 -7시간"}, "germany": {"code": "de", "tz": "한국 -7시간"},
    "오스트리아": {"code": "at", "tz": "한국 -7시간"}, "체코": {"code": "cz", "tz": "한국 -7시간"},
    "그리스": {"code": "gr", "tz": "한국 -6시간"},
    "uae": {"code": "ae", "tz": "한국 -5시간"}, "아랍에미리트": {"code": "ae", "tz": "한국 -5시간"},
    "두바이": {"code": "ae", "tz": "한국 -5시간"}
}

KNOWN_CITIES = {
    "로마": (41.9028, 12.4964), "파리": (48.8566, 2.3522), "피렌체": (43.7696, 11.2558),
    "베네치아": (45.4408, 12.3155), "바르셀로나": (41.3851, 2.1734), "런던": (51.5074, -0.1278),
    "프라하": (50.0755, 14.4378), "비엔나": (48.2082, 16.3738), "인터라켄": (46.6863, 7.8632),
    "두바이": (25.2048, 55.2708)
}

# 세션 상태 초기화
if 'search_result' not in st.session_state: st.session_state.search_result = None
if 'last_clicked' not in st.session_state: st.session_state.last_clicked = None
if 'last_country' not in st.session_state: st.session_state.last_country = "유럽 전체 보기"
if 'last_city' not in st.session_state: st.session_state.last_city = "전체 보기"
if 'daily_target_date' not in st.session_state:
    st.session_state.daily_target_date = datetime(2027, 4, 30).date()

def extract_coords(url):
    if not url or pd.isna(url): return None, None
    try:
        url_str = unquote(str(url))
        match = re.search(r'q=([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str) or \
                re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url_str)
        if match: return float(match.group(1)), float(match.group(2))
    except: pass
    return None, None

# --- 데이터 로드 및 정규화 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    raw_df = conn.read(spreadsheet=SHEET_URL, ttl=600)
    raw_df.columns = [str(c).strip() for c in raw_df.columns]
    
    for col in ["시작일", "종료일", "시간", "실제 일정", "국가", "도시", "장소명", "구글맵 링크", "카테고리"]:
        if col not in raw_df.columns:
            raw_df[col] = ""
        raw_df[col] = raw_df[col].astype(str).str.strip()
        raw_df[col] = raw_df[col].replace(['nan', 'None', 'NaT', 'none', 'nat'], "")
    
    for col in ["계획 비용", "실제 비용", "총 예산"]:
        if col not in raw_df.columns:
            raw_df[col] = 0
        raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0).astype(int)
        
    df = raw_df
except Exception as e:
    st.error(f"데이터 연결 오류: {e}")
    st.stop()

# --- 날짜 파싱 단일화 ---
city_ranges = []
for _, row in df[df['카테고리'] == '도시'].iterrows():
    if row['시작일'] and row['종료일']:
        try:
            city_ranges.append({
                'country': row['국가'],
                'city': row['도시'],
                'start': pd.to_datetime(row['시작일']).date(),
                'end': pd.to_datetime(row['종료일']).date()
            })
        except: pass

# --- 메인 UI ---
st.title("🛫")

# 라디오 버튼을 사용해 탭 렌더링 최적화
menu = st.radio("이동할 탭을 선택하세요", ["📍 방문 예정지", "📅 체류 일정", "💰 여행 가계부"], horizontal=True, label_visibility="collapsed")
st.write("---")

# ==========================================
# [화면 1] 방문 예정지
# ==========================================
if menu == "📍 방문 예정지":
    with st.expander("➕ 도시 추가", expanded=False):
        with st.form("add_city", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: add_country = st.text_input("국가", placeholder="예: 스페인")
            with c2: add_city = st.text_input("도시", placeholder="예: 바르셀로나")
            if st.form_submit_button("등록", use_container_width=True):
                if add_country and add_city:
                    lat, lon = KNOWN_CITIES.get(add_city, (None, None))
                    if not lat:
                        loc = get_cached_location(f"{add_city}, {add_country}")
                        if loc: lat, lon = loc['lat'], loc['lon']
                    if lat:
                        new_row = pd.DataFrame([{"국가": add_country, "도시": add_city, "장소명": f"{add_city} 중심", "구글맵 링크": f"https://www.google.com/maps?q={lat},{lon}", "카테고리": "도시"}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.cache_data.clear(); st.rerun()

    if not df.empty:
        col_sel, col_edit = st.columns([2, 8])
        with col_sel:
            countries = ["유럽 전체 보기"] + sorted(list(df["국가"].unique()))
            selected_country = st.selectbox("국가 선택", [c for c in countries if c])
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
                res = get_cached_location(search_q)
                if res:
                    st.session_state.search_result = res
                    st.session_state.last_clicked = None
                else: st.warning("장소를 찾을 수 없습니다.")

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
                        c_info = COUNTRY_INFO.get(re.sub(r'\s+', '', str(p['country']).lower()), {})
                        code = c_info.get("code", "")
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
                        new_row = pd.DataFrame([{"국가": selected_country if selected_country != "유럽 전체 보기" else "미정", "도시": selected_city if selected_city != "전체 보기" else "미정", "장소명": s_name, "구글맵 링크": f"https://www.google.com/maps?q={target['lat']},{target['lon']}", "카테고리": s_cat}])
                        conn.update(spreadsheet=SHEET_URL, data=pd.concat([df, new_row], ignore_index=True))
                        st.session_state.search_result = st.session_state.last_clicked = None; st.cache_data.clear(); st.rerun()

            st.divider()
            st.subheader("📋 전체 데이터 편집")
            edited = st.data_editor(display_df, use_container_width=True, hide_index=True, num_rows="dynamic")
            if st.button("💾 시트 변경사항 저장", key="save_btn_1"):
                other = df[~df.index.isin(display_df.index)]
                conn.update(spreadsheet=SHEET_URL, data=pd.concat([other, edited], ignore_index=True))
                st.cache_data.clear(); st.rerun()

# ==========================================
# [화면 2] 체류 일정 (먹통 방지 안전 클릭 달력)
# ==========================================
elif menu == "📅 체류 일정":
    cal_c1, cal_c2, _ = st.columns([1, 1, 8])
    with cal_c1: sel_year = st.selectbox("연도", [2026, 2027, 2028], index=1, key="cal_year")
    with cal_c2: sel_month = st.selectbox("월", list(range(1, 13)), index=3, key="cal_month") # 4월 기본 지정
    st.write("---")

    # [핵심 수술] Column 전체를 마비시키는 코드를 버리고, 오직 '버튼 하나'만 살짝 위로 올려 덮는 가장 안전한 방식 도입!
    st.markdown("""
        <style>
        /* HTML로 그리는 사각칸의 높이를 무조건 100px로 고정합니다. */
        .cal-cell {
            height: 100px;
            border-radius: 8px;
            padding: 5px;
            text-align: center;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        
        /* 버튼을 감싸는 기본 컨테이너가 공간을 차지하지 않도록 높이를 0으로 만듭니다. */
        div.element-container:has(button[title="cal_click"]) {
            position: relative !important;
            height: 0px !important;
            min-height: 0px !important;
            margin: 0 !important;
            padding: 0 !important;
            z-index: 10 !important;
        }
        
        /* 투명 버튼을 카드 위로 정확히 112px만큼 당겨 올려서 완벽하게 포갭니다. */
        button[title="cal_click"] {
            position: absolute !important;
            top: -112px !important;
            left: 0 !important;
            width: 100% !important;
            height: 105px !important;
            background-color: transparent !important;
            border: 2px solid transparent !important;
            color: transparent !important;
            box-shadow: none !important;
            cursor: pointer !important;
        }
        
        /* 버튼에 마우스를 올리거나 클릭하면 빨간 테두리 효과 발생! */
        button[title="cal_click"]:hover {
            border: 2px solid #ff4b4b !important;
            background-color: rgba(255, 75, 75, 0.05) !important;
            border-radius: 8px !important;
        }
        
        /* 못생긴 스트림릿 버튼 글자 원천 차단 */
        button[title="cal_click"] p {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # 국기 정보 사전 렌더링
    flag_schedule = {}
    for cr in city_ranges:
        code = COUNTRY_INFO.get(re.sub(r'\s+', '', str(cr['country']).lower()), {}).get("code", "")
        flag_img = f"<img src='https://flagcdn.com/w40/{code}.png' style='width:32px; border-radius:3px; box-shadow:1px 1px 3px rgba(0,0,0,0.2); margin:2px;'>" if code else "📍"
        
        curr_dt = cr['start']
        while curr_dt <= cr['end']:
            if curr_dt.year == sel_year and curr_dt.month == sel_month:
                if curr_dt.day in flag_schedule and flag_img not in flag_schedule[curr_dt.day]:
                    flag_schedule[curr_dt.day] += f" {flag_img}"
                elif curr_dt.day not in flag_schedule:
                    flag_schedule[curr_dt.day] = flag_img
            curr_dt += timedelta(days=1)

    # 요일 헤더
    h_cols = st.columns(7)
    days_title = [("일", "red"), ("월", "gray"), ("화", "gray"), ("수", "gray"), ("목", "gray"), ("금", "gray"), ("토", "blue")]
    for idx, (d_name, color) in enumerate(days_title):
        h_cols[idx].markdown(f"<div style='text-align:center; font-weight:bold; font-size:16px; color:{color}; padding-bottom:5px; border-bottom:2px solid #eee;'>{d_name}</div>", unsafe_allow_html=True)
    st.write("")

    cal = calendar.monthcalendar(sel_year, sel_month)
    
    # 달력 본문
    for week in cal:
        w_cols = st.columns(7)
        for i, day in enumerate(week):
            with w_cols[i]:
                if day == 0:
                    # 일정이 없는 빈 날짜 칸
                    st.markdown("<div class='cal-cell' style='background-color: #f9f9f9;'></div>", unsafe_allow_html=True)
                else:
                    is_selected = (st.session_state.daily_target_date == datetime(sel_year, sel_month, day).date())
                    day_color = "red" if i == 0 else "blue" if i == 6 else "black"
                    flags = flag_schedule.get(day, "<div style='height:36px;'></div>")
                    
                    # 오리지널 예쁜 사각 디자인 + 선택 시 빨간 테두리!
                    border_css = "border: 2px solid #ff4b4b; background-color: rgba(255, 75, 75, 0.03);" if is_selected else "border: 1px solid rgba(128,128,128,0.2); background-color: white;"
                    
                    st.markdown(f"""
                        <div class='cal-cell' style='{border_css}'>
                            <div style='font-size:16px; font-weight:bold; color:{day_color};'>{day}</div>
                            <div style='display:flex; justify-content:center; flex-wrap:wrap; gap:2px; margin-top:2px;'>{flags}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 마법의 투명 버튼 (클릭 감지기)
                    if st.button("ㅤ", help="cal_click", key=f"cal_btn_{sel_year}_{sel_month}_{day}", use_container_width=True):
                        st.session_state.daily_target_date = datetime(sel_year, sel_month, day).date()
                        st.rerun()

    st.write("---")
    
    # [일일 상세 일정 네비게이터 & 타임라인]
    target_date = st.session_state.daily_target_date
    weekday_kr = ["일", "월", "화", "수", "목", "금", "토"][target_date.weekday() if target_date.weekday() == 6 else target_date.weekday() + 1]
    if target_date.weekday() == 6: weekday_kr = "일"
    else: weekday_kr = ["월", "화", "수", "목", "금", "토"][target_date.weekday()]
    
    nav_c1, nav_c2, nav_c3 = st.columns([1.5, 7, 1.5])
    with nav_c1:
        if st.button("◀ 이전 날", use_container_width=True):
            st.session_state.daily_target_date -= timedelta(days=1)
            st.rerun()
    with nav_c3:
        if st.button("다음 날 ▶", use_container_width=True):
            st.session_state.daily_target_date += timedelta(days=1)
            st.rerun()
    with nav_c2:
        st.markdown(f"<h3 style='text-align:center; margin:0;'>⏱️ {target_date.strftime('%Y년 %m월 %d일')} ({weekday_kr}) 상세 일정</h3>", unsafe_allow_html=True)

    # 오버랩 렌더링
    overlapping_places = [cr for cr in city_ranges if cr['start'] <= target_date <= cr['end']]
    current_country, current_city = "", ""
    
    if overlapping_places:
        header_html = ""
        c_names, city_names = [], []
        
        for i, place in enumerate(overlapping_places):
            cntry, cty = place['country'], place['city']
            c_info = COUNTRY_INFO.get(re.sub(r'\s+', '', cntry.lower()), {})
            code = c_info.get("code", "")
            tz_txt = c_info.get("tz", "")
            
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
                daily_df.loc[idx, "계획 일정"] = r["장소명"]
                daily_df.loc[idx, "계획 지출액"] = r["계획 비용"]
                daily_df.loc[idx, "실제 방문"] = r["실제 일정"]
                daily_df.loc[idx, "실제 지출액"] = r["실제 비용"]

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
                append_list.append({
                    "국가": current_country, "도시": current_city,
                    "장소명": r["계획 일정"], "카테고리": "일정", "시작일": str(target_date),
                    "시간": r["시간"], "계획 비용": r["계획 지출액"], 
                    "실제 일정": r["실제 방문"], "실제 비용": r["실제 지출액"],
                    "총 예산": df["총 예산"].max() if not df.empty else 0
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
                    updated_df.loc[mask, "시작일"] = s_val.strftime("%Y-%m-%d") if pd.notnull(s_val) else ""
                    updated_df.loc[mask, "종료일"] = e_val.strftime("%Y-%m-%d") if pd.notnull(e_val) else ""
                conn.update(spreadsheet=SHEET_URL, data=updated_df)
                st.cache_data.clear(); st.rerun()
            except Exception as e: st.error("저장 실패.")

# ==========================================
# [화면 3] 여행 가계부
# ==========================================
elif menu == "💰 여행 가계부":
    st.subheader("💰 전체 여행 가계부")
    current_budget = df["총 예산"].max() if not df.empty else 0
        
    with st.form("budget_form"):
        new_budget = st.number_input("총 여행 예산 입력 (원)", min_value=0, step=100000, value=int(current_budget))
        if st.form_submit_button("예산 저장", type="primary"):
            if not df.empty:
                df["총 예산"] = new_budget
                conn.update(spreadsheet=SHEET_URL, data=df)
                st.success("총 예산이 업데이트되었습니다!")
                st.cache_data.clear(); st.rerun()

    st.write("---")
    schedule_rows = df[df["카테고리"] == "일정"]
    total_planned_cost = schedule_rows["계획 비용"].sum()
    total_actual_cost = schedule_rows["실제 비용"].sum()
    
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
