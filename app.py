import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium

# 페이지 설정 (미니멀 & 와이드 레이아웃)
st.set_page_config(page_title="Honeymoon Planner", layout="wide")

# 1. 구글 시트 연결 (URL에 본인의 시트 주소를 넣으세요)
# URL 끝부분의 /edit#gid=0 을 /export?format=csv 로 변경해야 합니다.
SHEET_URL = "https://docs.google.com/spreadsheets/d/1BVAUJ05mVkzgi2dprZ1w60b34YifUlZGxnVehPzO4aE/export?format=csv"

@st.cache_data(ttl=600) # 10분마다 데이터 새로고침
def load_data(url):
    df = pd.read_csv(url)
    return df

try:
    df = load_data(SHEET_URL)

    st.title("💍 2027 유럽 신혼여행 계획")
    st.info("구글 스프레드시트와 실시간 연동 중입니다. 시트 내용을 수정하고 10분 뒤 혹은 페이지를 새로고침하면 반영됩니다.")

    # 2. 사이드바: 위계형 필터 (국가 -> 도시 -> 카테고리)
    st.sidebar.header("📍 여행지 탐색")
    
    countries = sorted(df["국가"].unique())
    selected_country = st.sidebar.selectbox("1. 국가 선택", countries)

    cities = sorted(df[df["국가"] == selected_country]["도시"].unique())
    selected_city = st.sidebar.selectbox("2. 도시 선택", cities)

    categories = ["전체"] + sorted(df[(df["국가"] == selected_country) & (df["도시"] == selected_city)]["카테고리"].unique().tolist())
    selected_category = st.sidebar.selectbox("3. 카테고리 선택", categories)

    # 데이터 필터링
    filtered_df = df[(df["국가"] == selected_country) & (df["도시"] == selected_city)]
    if selected_category != "전체":
        filtered_df = filtered_df[filtered_df["카테고리"] == selected_category]

    # 3. 메인 화면: 지도와 리스트
    col1, col2 = st.columns([1.5, 1])

    with col1:
        st.subheader(f"🗺️ {selected_city} 지역 지도")
        # 데이터에 위도/경도가 있을 경우 지도 표시
        if "위도" in filtered_df.columns and not filtered_df["위도"].isnull().all():
            m = folium.Map(location=[filtered_df["위도"].mean(), filtered_df["경도"].mean()], zoom_start=13)
            for _, row in filtered_df.iterrows():
                folium.Marker(
                    [row["위도"], row["경도"]],
                    popup=row["장소명"],
                    tooltip=f"{row['장소명']} ({row['카테고리']})",
                    icon=folium.Icon(color="red" if row["우선순위"] >= 5 else "blue")
                ).add_to(m)
            st_folium(m, width="100%", height=500)
        else:
            st.warning("시트에 위도/경도 정보를 입력하면 지도가 활성화됩니다.")

    with col2:
        st.subheader("📋 장소 우선순위 리스트")
        # 우선순위 높은 순으로 정렬하여 표시
        display_df = filtered_df.sort_values(by="우선순위", ascending=False)
        st.dataframe(
            display_df[["장소명", "카테고리", "우선순위", "메모", "구글맵 링크"]],
            use_container_width=True,
            hide_index=True
        )

except Exception as e:
    st.error(f"데이터를 불러오지 못했습니다. 시트 URL과 공유 설정을 확인해주세요. 에러: {e}")
