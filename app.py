import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
import re

# 1. 시트 ID 설정 (여기에 본인의 시트 ID만 정확히 넣어주세요)
# 주소창 d/ 와 /edit 사이의 값입니다. 
# 예: 1abc123456789...
MY_ID = "1BVAUJ05mVkzgi2dprZ1w60b34YifUlZGxnVehPzO4aE"

st.set_page_config(page_title="유럽 신혼여행 플래너", layout="wide")

def get_sheet_url(id_input):
    # 주소 전체를 넣었을 경우 ID만 추출
    clean_id = re.search(r"/d/([a-zA-Z0-9-_]+)", id_input)
    target_id = clean_id.group(1) if clean_id else id_input
    return f"https://docs.google.com/spreadsheets/d/{target_id}/export?format=csv"

try:
    SHEET_URL = get_sheet_url(MY_ID)
    
    # 데이터 불러오기
    @st.cache_data(ttl=10)
    def load_data(url):
        # 한글 깨짐 방지 인코딩 추가
        return pd.read_csv(url)

    df = load_data(SHEET_URL)
    
    # [중요] 모든 열 이름의 앞뒤 공백을 강제로 제거합니다.
    df.columns = df.columns.str.strip()

    st.title("💍 2027 유럽 신혼여행 플래너")

    # --- 디버깅 섹션 (에러 발생 시 확인용) ---
    if "국가" not in df.columns:
        st.error("🚨 시트의 첫 번째 줄(제목)을 확인해 주세요!")
        st.write("프로그램이 찾은 제목들:", df.columns.tolist())
        st.info("팁: 시트 A1 셀에 '국가', B1 셀에 '도시'라고 정확히 적혀 있나요?")
        st.stop()
    # ---------------------------------------

    # 사이드바 필터
    st.sidebar.header("📍 여행지 탐색")
    countries = sorted(df["국가"].dropna().unique())
    selected_country = st.sidebar.selectbox("1. 국가 선택", countries)

    cities = sorted(df[df["국가"] == selected_country]["도시"].dropna().unique())
    selected_city = st.sidebar.selectbox("2. 도시 선택", cities)

    # 메인 화면
    col1, col2 = st.columns([1.5, 1])
    filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)]

    with col1:
        st.subheader(f"🗺️ {selected_city} 지도")
        if "위도" in filtered_df.columns and not filtered_df["위도"].isnull().all():
            m = folium.Map(location=[filtered_df["위도"].mean(), filtered_df["경도"].mean()], zoom_start=12)
            for _, row in filtered_df.iterrows():
                if pd.notna(row["위도"]):
                    folium.Marker([row["위도"], row["경도"]], popup=row.get("장소명", "Point")).add_to(m)
            st_folium(m, width="100%", height=500)
        else:
            st.warning("위도/경도 데이터가 없어 지도를 표시할 수 없습니다.")

    with col2:
        st.subheader("📋 목록")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error("연결 오류가 발생했습니다.")
    st.write("확인할 점:")
    st.write("1. MY_ID 변수에 시트 ID를 정확히 넣으셨나요? (따옴표 안에 한글이 섞이면 안 됩니다)")
    st.write(f"2. 실제 에러 내용: {e}")