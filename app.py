import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re
from urllib.parse import unquote

# 페이지 설정
st.set_page_config(page_title="유럽 신혼여행 플래너", layout="wide")

SHEET_ID = "1BVAUJ05mVkzgi2dprZ1w60b34YifUlZGxnVehPzO4aE"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

def extract_coords_from_url(url):
    """구글맵 URL에서 위도/경도 자동 추출"""
    if pd.isna(url) or not isinstance(url, str):
        return None, None
    url = unquote(url)
    match = re.search(r'@([-+]?\d+\.\d+),([-+]?\d+\.\d+)', url)
    if match: return float(match.group(1)), float(match.group(2))
    match = re.search(r'!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)', url)
    if match: return float(match.group(1)), float(match.group(2))
    return None, None

@st.cache_data(ttl=10)
def load_and_process_data(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    
    if "위도" not in df.columns: df["위도"] = None
    if "경도" not in df.columns: df["경도"] = None
    
    if "구글맵 링크" in df.columns:
        for idx, row in df.iterrows():
            if pd.isna(row.get("위도")) or pd.isna(row.get("경도")):
                lat, lon = extract_coords_from_url(row["구글맵 링크"])
                if lat and lon:
                    df.at[idx, "위도"] = lat
                    df.at[idx, "경도"] = lon
    return df

try:
    df = load_and_process_data(SHEET_URL)

    st.title("🇪🇺 2027 유럽 신혼여행 플래너")
    
    if df.empty:
        st.warning("데이터가 없습니다. 구글 시트에 내용을 입력해 주세요.")
        st.stop()

    # 사이드바
    st.sidebar.header("📍 여행지 탐색")
    
    # [새로운 팁] 시트로 바로가는 버튼을 앱에 추가
    st.sidebar.markdown("---")
    st.sidebar.write("✍️ **진짜 앱처럼 데이터 추가하기**")
    st.sidebar.link_button("새 장소 영구 저장하기 (시트 열기)", f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    st.sidebar.markdown("---")

    countries = sorted(df["국가"].dropna().unique())
    selected_country = st.sidebar.selectbox("1. 국가 선택", countries)

    cities = sorted(df[df["국가"] == selected_country]["도시"].dropna().unique())
    selected_city = st.sidebar.selectbox("2. 도시 선택", cities)

    filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)]

    col1, col2 = st.columns([1.5, 1])

    with col1:
        st.subheader(f"🗺️ {selected_city} 지도")
        filtered_df["위도"] = pd.to_numeric(filtered_df["위도"], errors='coerce')
        filtered_df["경도"] = pd.to_numeric(filtered_df["경도"], errors='coerce')
        
        map_data = filtered_df.dropna(subset=["위도", "경도"])
        
        if not map_data.empty:
            m = folium.Map(location=[map_data["위도"].mean(), map_data["경도"].mean()], zoom_start=13)
            for _, row in map_data.iterrows():
                priority = row.get("우선순위", 0)
                folium.Marker(
                    [row["위도"], row["경도"]],
                    popup=row.get("장소명", "Point"),
                    tooltip=f"{row.get('장소명')} ({row.get('카테고리', '미분류')})",
                    icon=folium.Icon(color="red" if priority >= 5 else "blue")
                ).add_to(m)
            st_folium(m, width="100%", height=500)
        else:
            st.info("💡 표에 '구글맵 링크'를 넣으시면 지도가 나타납니다.")

    with col2:
        st.subheader("📋 목록 (더블클릭하여 수정하세요!)")
        # [수정됨] 구글맵 링크를 화면에 다시 노출
        cols_to_show = [c for c in ["장소명", "카테고리", "우선순위", "구글맵 링크", "메모"] if c in filtered_df.columns]
        
        # [수정됨] 단순 표가 아니라 직접 수정 가능한 에디터로 변경
        st.data_editor(
            filtered_df[cols_to_show],
            use_container_width=True,
            hide_index=True,
            column_config={
                "구글맵 링크": st.column_config.LinkColumn("구글맵 🗺️") # 링크를 클릭 가능하게 변환
            }
        )
        st.caption("※ 앱 내에서 수정한 내용은 임시 시뮬레이션 용도입니다. 영구적인 저장은 좌측의 '새 장소 추가하기' 버튼을 이용해 주세요.")

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
