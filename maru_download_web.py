import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
from io import BytesIO


def get_reg_cd_from_site(site, json_data):
    try:
        reg_cd = next(item['번호'] for item in json_data if item['지역명'] == site)
        reg_cd = str(reg_cd) + '00000'
        return reg_cd
    except StopIteration:
        st.error(f"지역명 {site}에 해당하는 reg_cd를 찾을 수 없습니다.")
        return None


def fetch_forecast_data(base_date, reg_cd):
    url = "https://bd.kma.go.kr/kma2020/energy/energyGeneration.do"
    params = {
        'baseDate': base_date,
        'fcstTime': 1000,
        'regCd': reg_cd
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.text
        data = json.loads(data)
        result = data['result']
        df = pd.DataFrame(result)

        try:
            df['baseDate'] = pd.to_datetime(df['baseDate'], format='%Y%m%d')
            df['fcstDate'] = pd.to_datetime(df['fcstDate'], format='%Y%m%d')
        except KeyError:
            return pd.DataFrame(), pd.DataFrame()

        df['regCd'] = reg_cd

        today = df[df['baseDate'] == df['fcstDate']]
        tomorrow = df[df['baseDate'] != df['fcstDate']]
        return today, tomorrow
    else:
        return pd.DataFrame(), pd.DataFrame()


def process_weather_data(base_date, reg_cd, site):
    today, tomorrow = fetch_forecast_data(base_date, reg_cd)

    if today.empty and tomorrow.empty:
        return pd.DataFrame(), pd.DataFrame()

    today = today[['fcstDate', 'fcstTime', 'srad', 'regCd', 'temp', 'wspd']]
    tomorrow = tomorrow[['fcstDate', 'fcstTime', 'srad', 'regCd', 'temp', 'wspd']]

    today['fcstTime'] = today['fcstTime'].apply(
        lambda x: pd.to_datetime(str(x).zfill(4), format='%H%M').strftime('%H:%M'))
    tomorrow['fcstTime'] = tomorrow['fcstTime'].apply(
        lambda x: pd.to_datetime(str(x).zfill(4), format='%H%M').strftime('%H:%M'))

    today['fcstDate'] = pd.to_datetime(today['fcstDate'])
    tomorrow['fcstDate'] = pd.to_datetime(tomorrow['fcstDate'])

    today['tm'] = today.apply(lambda row: pd.to_datetime(f"{row['fcstDate'].strftime('%Y-%m-%d')} {row['fcstTime']}"),
                              axis=1)
    tomorrow['tm'] = tomorrow.apply(
        lambda row: pd.to_datetime(f"{row['fcstDate'].strftime('%Y-%m-%d')} {row['fcstTime']}"), axis=1)

    today = today.rename(columns={'srad': '예측광량', 'regCd': '지역코드', 'temp': '예측온도', 'wspd': '예측풍속'})
    tomorrow = tomorrow.rename(columns={'srad': '예측광량', 'regCd': '지역코드', 'temp': '예측온도', 'wspd': '예측풍속'})

    today['지역명'] = site
    tomorrow['지역명'] = site
    return today, tomorrow


def save_filtered_data_by_month(df):
    csv_data = BytesIO()
    df.to_csv(csv_data, index=False, encoding='utf-8-sig')
    csv_data.seek(0)
    return csv_data


def main():
    # 사이드바에 선택 옵션 추가
    page = st.sidebar.selectbox("페이지 선택", ["서비스 설명", "기상 데이터 다운로드"])

    # JSON 파일을 로컬에서 읽기
    json_file_path = './assets/site_code.json'
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        if page == "서비스 설명":
            st.title("날씨마루 예측 기상 자료 다운로드")
            st.write("""
            날씨마루는 태양광발전량예측을 위한 당일/다음날의 예측 광량, 온도, 풍속 데이터를 제공합니다.
            URL: https://bd.kma.go.kr/kma2020/fs/energySelect1.do?pageNum=5&menuCd=F050701000

            - 시작 날짜와 종료 날짜를 설정하고, 지역명을 입력하면 해당 기간 동안의 기상 데이터를 다운로드할 수 있습니다.
            - 기상 데이터에는 일사량, 온도, 풍속 등의 정보가 포함되어 있습니다.
            - 데이터는 지역별로 JSON 파일을 기반으로 검색할 수 있습니다.

            **사용 방법**
            1. 좌측의 "기상 데이터 다운로드" 페이지로 이동합니다.
            2. 시작 날짜와 종료 날짜를 선택합니다.
            3. 지역명을 선택합니다.
            4. 데이터를 찾고 다운로드 버튼을 클릭하여 데이터를 저장합니다.
            """)

            # JSON 파일에서 사이트 정보 추출
            site_data = pd.DataFrame(json_data)

            # 사이트 목록을 테이블로 표시
            st.subheader("다운로드 가능한 지역 목록")
            st.table(site_data[['지역명', '번호']])

        elif page == "기상 데이터 다운로드":
            st.title("날씨마루 기상 데이터 다운로드")

            # 날짜 입력 받기
            start_date = st.date_input("시작 날짜", value=datetime.today().replace(day=1))
            end_date = st.date_input("종료 날짜", value=datetime.today())

            # JSON 파일에서 지역명 목록 추출
            site_names = [item['지역명'] for item in json_data]

            # 지역명을 선택할 수 있는 선택 박스 추가
            site = st.selectbox("지역명 선택", site_names, index=0)

            reg_cd = get_reg_cd_from_site(site, json_data)

            if reg_cd and st.button('찾기'):
                base_dates = pd.date_range(start=start_date, end=end_date).strftime('%Y%m%d')

                all_today_df = pd.DataFrame()
                all_tomorrow_df = pd.DataFrame()

                # 프로그레스 바 생성
                progress_bar = st.progress(0)
                total_dates = len(base_dates)

                # 데이터를 처리
                for i, date in enumerate(base_dates):
                    today_df, tomorrow_df = process_weather_data(date, reg_cd, site)
                    all_today_df = pd.concat([all_today_df, today_df], ignore_index=True)
                    all_tomorrow_df = pd.concat([all_tomorrow_df, tomorrow_df], ignore_index=True)

                    # 프로그레스 바 업데이트
                    progress_bar.progress((i + 1) / total_dates)

                # 프로그레스 바 완료
                progress_bar.empty()

                # CSV 파일 저장 및 다운로드 버튼 추가
                if not all_today_df.empty:
                    today_csv = save_filtered_data_by_month(all_today_df)
                    st.download_button(label="오늘 데이터 CSV 다운로드", data=today_csv, file_name="today_weather.csv",
                                       mime="text/csv")

                if not all_tomorrow_df.empty:
                    tomorrow_csv = save_filtered_data_by_month(all_tomorrow_df)
                    st.download_button(label="내일 데이터 CSV 다운로드", data=tomorrow_csv, file_name="tomorrow_weather.csv",
                                       mime="text/csv")
    except FileNotFoundError:
        st.error(f"JSON 파일을 찾을 수 없습니다: {json_file_path}")


if __name__ == "__main__":
    main()
