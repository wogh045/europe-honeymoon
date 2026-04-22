import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
from urllib.parse import unquote
from streamlit_gsheets import GSheetsConnection

# 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너 Pro", layout="wide")

# 시트 URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1BVAUJ05mVkzgi2dprZ1w60b34YifUlZGxnVehPzO4aE/edit"

def extract_coords(url):
    """구글맵 URL에서 위도/경도 자동 추출"""
    if pd.isna(url) or not isinstance(url, str): return None, None
    url = unquote(url)
    match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url)
    if match: return float(match.group(1)), float(match.group(2))
    match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url)
    if match: return float(match.group(1)), float(match.group(2))
    return None, None

try:
    # 1. GCP 연결을 통해 데이터 가져오기 (GSheetsConnection 사용)
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=SHEET_URL)
    df.columns = df.columns.str.strip()

    st.title("💍 2027 유럽 신혼여행 플래너 (Admin Mode)")
    st.markdown("이 앱에서 수정하는 모든 내용은 구글 스프레드시트에 실시간으로 반영됩니다.")

    # 2. 새로운 장소 추가 섹션 (Expander 사용)
    with st.expander("➕ 새로운 여행지 추가하기"):
        with st.form("add_place_form", clear_on_submit=True):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                new_country = st.text_input("국가", placeholder="예: 이탈리아")
                new_city = st.text_input("도시", placeholder="예: 로마")
            with col_b:
                new_place = st.text_input("장소명", placeholder="예: 트레비 분수")
                new_category = st.selectbox("카테고리", ["관광지", "맛집", "숙소", "교통", "기타"])
            with col_c:
                new_url = st.text_input("구글맵 링크", placeholder="주소창 전체 URL 붙여넣기")
                new_priority = st.slider("우선순위", 1, 5, 3)
            
            new_memo = st.text_area("메모", placeholder="이 장소에 대한 간단한 생각")
            submit_button = st.form_submit_button("시트에 영구 저장")

            if submit_button:
                if new_country and new_city and new_place:
                    # 새로운 행 생성
                    new_row = pd.DataFrame([{
                        "국가": new_country, "도시": new_city, "장소명": new_place,
                        "카테고리": new_category, "구글맵 링크": new_url,
                        "우선순위": new_priority, "메모": new_memo
                    }])
                    updated_df = pd.concat([df, new_row], ignore_index=True)
                    # 구글 시트에 업데이트
                    conn.update(spreadsheet=SHEET_URL, data=updated_df)
                    st.success(f"'{new_place}' 장소가 성공적으로 추가되었습니다!")
                    st.cache_data.clear() # 데이터 새로고침 유도
                    st.rerun()
                else:
                    st.error("국가, 도시, 장소명은 필수 입력 항목입니다.")

    st.divider()

    # 3. 탐색 및 관리 섹션
    st.sidebar.header("📍 여행지 탐색")
    if not df.empty:
        countries = sorted(df["국가"].dropna().unique())
        selected_country = st.sidebar.selectbox("1. 국가 선택", countries)
        cities = sorted(df[df["국가"] == selected_country]["도시"].dropna().unique())
        selected_city = st.sidebar.selectbox("2. 도시 선택", cities)

        # 현재 보고 있는 데이터 필터링
        filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)].copy()

        col_left, col_right = st.columns([1.2, 1.5])

        with col_left:
            st.subheader(f"🗺️ {selected_city} 지도")
            # 지도용 데이터 가공 (좌표 추출)
            map_df = filtered_df.copy()
            for idx, row in map_df.iterrows():
                if pd.isna(row.get("위도")) or pd.isna(row.get("경도")):
                    lat, lon = extract_coords(row.get("구글맵 링크"))
                    if lat and lon:
                        map_df.at[idx, "위도"] = lat
                        map_df.at[idx, "경도"] = lon
            
            map_df["위도"] = pd.to_numeric(map_df["위도"], errors='coerce')
            map_df["경도"] = pd.to_numeric(map_df["경도"], errors='coerce')
            valid_map = map_df.dropna(subset=["위도", "경도"])
            
            if not valid_map.empty:
                m = folium.Map(location=[valid_map["위도"].mean(), valid_map["경도"].mean()], zoom_start=13)
                for _, row in valid_map.iterrows():
                    p = pd.to_numeric(row.get("우선순위", 0), errors='coerce')
                    folium.Marker(
                        [row["위도"], row["경도"]],
                        popup=row.get("장소명", "Point"),
                        tooltip=f"{row.get('장소명')} ({row.get('카테고리', '')})",
                        icon=folium.Icon(color="red" if p == 5 else "blue")
                    ).add_to(m)
                st_folium(m, width="100%", height=500, key=f"map_{selected_city}")
            else:
                st.info("구글맵 링크를 입력하시면 지도가 활성화됩니다.")

        with col_right:
            st.subheader("📋 데이터 관리 (수정/삭제)")
            st.write("표 안의 내용을 직접 수정하거나, 행을 선택해 삭제할 수 있습니다.")
            
            # 직접 수정 가능한 에디터
            edited_df = st.data_editor(
                filtered_df,
                num_rows="dynamic", # 행 추가/삭제 가능
                use_container_width=True,
                hide_index=True,
                column_config={
                    "구글맵 링크": st.column_config.LinkColumn("구글맵 🗺️"),
                    "우선순위": st.column_config.NumberColumn(min_value=1, max_value=5, step=1)
                }
            )

            if st.button("💾 변경사항 시트에 영구 저장", type="primary"):
                # 전체 데이터에서 해당 도시 부분 교체
                final_df = df[~((df["국가"] == selected_country) & (df["도시"] == selected_city))]
                final_df = pd.concat([final_df, edited_df], ignore_index=True)
                
                conn.update(spreadsheet=SHEET_URL, data=final_df)
                st.success("데이터가 성공적으로 업데이트되었습니다!")
                st.cache_data.clear()
                st.rerun()

except Exception as e:
    st.error("연결 오류가 발생했습니다. Secrets 설정과 시트 공유 권한을 확인해 주세요.")
    st.write(f"에러 메시지: {e}")
