# 💡 [변경] 이모지 대신 이미지 국기를 가져오기 위한 국가 코드표
FLAG_CODES = {
    "이탈리아": "it", "프랑스": "fr", "스위스": "ch", "스페인": "es",
    "영국": "gb", "독일": "de", "오스트리아": "at", "체코": "cz",
    "포르투갈": "pt", "그리스": "gr"
}

# (중간 코드 동일: extract_coords, 데이터 연결, 레이아웃 등)
# ... valid_points 정리 후 지도 그리는 부분 ...

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
        
        for p in valid_points:
            # 1. '도시' 카테고리일 경우 확실한 이미지 국기 적용
            if p['cat'] == "도시":
                country_code = FLAG_CODES.get(p['country'], "")
                
                if country_code:
                    # flagcdn.com에서 실제 국기 이미지를 가져와서 지도 위에 올립니다.
                    html_content = f'''
                        <div style="text-align: center;">
                            <img src="https://flagcdn.com/w40/{country_code}.png" 
                                 style="width: 32px; border: 1px solid #ddd; border-radius: 4px; box-shadow: 2px 2px 5px rgba(0,0,0,0.4);">
                        </div>
                    '''
                    custom_icon = folium.DivIcon(html=html_content)
                else:
                    # 목록에 없는 국가는 기본 핀
                    custom_icon = folium.DivIcon(html='<div style="font-size: 30px; text-shadow: 2px 2px 4px rgba(0,0,0,0.4);">📍</div>')
            
            # 2. 나머지 카테고리는 일반 아이콘 적용 (유지)
            else:
                color = "red" if p['cat'] == "관광지" else "orange" if p['cat'] == "맛집" else "green" if p['cat'] == "숙소" else "purple" if p['cat'] == "교통시설" else "blue"
                icon_shape = "camera" if p['cat'] == "관광지" else "cutlery" if p['cat'] == "맛집" else "bed" if p['cat'] == "숙소" else "info-sign"
                custom_icon = folium.Icon(color=color, icon=icon_shape)

            folium.Marker(
                [p['lat'], p['lon']], 
                popup=f"({p['city']}) {p['name']}", 
                tooltip=f"[{p['cat']}] {p['name']}", 
                icon=custom_icon
            ).add_to(m)
        
        st_folium(m, width="100%", height=500, key=f"map_{selected_country}_{selected_city}")
