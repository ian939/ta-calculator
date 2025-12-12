import streamlit as st
import pandas as pd
import holidays
from datetime import date, timedelta, datetime

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 디자인
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="T&A Auto Calculator",
    page_icon="📅",
    layout="wide"
)

st.title("👕 글로벌 소싱 T&A 자동 계산기")
st.markdown("""
바이어의 **납기일(In Store Date)**만 입력하세요.  
국가별 휴일과 공장 가동 현실을 반영하여 **최적의 발주 시점(Booking Date)**을 자동으로 계산합니다.
""")
st.divider()

# -----------------------------------------------------------------------------
# 2. 핵심 로직: 휴일 계산 엔진
# -----------------------------------------------------------------------------
@st.cache_data # 속도 향상을 위해 데이터 캐싱
def get_holidays(year, country_code):
    """라이브러리에서 휴일을 가져오고, 공장용 장기 휴무(Buffer)를 추가합니다."""
    holiday_set = set()
    
    # 국가별 휴일 로드
    if country_code == 'CHINA':
        raw_holidays = holidays.CN(years=[year, year-1])
    elif country_code == 'VIETNAM':
        raw_holidays = holidays.VN(years=[year, year-1])
    elif country_code == 'CAMBODIA':
        try: raw_holidays = holidays.KH(years=[year, year-1])
        except: raw_holidays = {}
    elif country_code == 'INDONESIA':
        raw_holidays = holidays.ID(years=[year, year-1])
    else:
        raw_holidays = {}

    # 공장 현실 반영 (Rule-Based Buffer)
    for hol_date, hol_name in raw_holidays.items():
        holiday_set.add(hol_date)
        
        # 춘절(CNY), 뗏(Tet) 등 대명절은 앞뒤로 5일씩 강제 휴무 추가
        if any(x in hol_name for x in ["New Year", "Spring Festival", "Tet", "Pchum Ben"]):
            for i in range(1, 6): # +5일, -5일 버퍼
                holiday_set.add(hol_date - timedelta(days=i))
                holiday_set.add(hol_date + timedelta(days=i))
                
    return holiday_set

def subtract_business_days(start_date, days, country):
    """주말과 휴일을 건너뛰며 날짜를 역산합니다."""
    current = start_date
    days_left = days
    impact_days = 0
    
    # 초기 휴일 데이터 로드
    holidays_data = get_holidays(current.year, country)

    while days_left > 0:
        current -= timedelta(days=1)
        
        # 연도가 바뀌면 휴일 데이터 갱신
        if current.year != (current + timedelta(days=1)).year:
            holidays_data = get_holidays(current.year, country)

        # 1. 주말 체크 (토, 일)
        if current.weekday() >= 5:
            continue
            
        # 2. 휴일 체크
        if current in holidays_data:
            impact_days += 1
            continue
            
        days_left -= 1
        
    return current, impact_days

# -----------------------------------------------------------------------------
# 3. 사이드바 (입력 메뉴)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("📝 입력 조건 (Input)")
    
    target_date = st.date_input(
        "매장 입고일 (In Store Date)",
        value=date(2026, 9, 14),
        min_value=date(2025, 1, 1)
    )
    
    col1, col2 = st.columns(2)
    with col1:
        fabric_origin = st.selectbox("원단 생산 (Fabric)", ["CHINA", "VIETNAM", "INDONESIA"])
    with col2:
        sewing_origin = st.selectbox("봉제 공장 (Sewing)", ["VIETNAM", "CAMBODIA", "INDONESIA"])
        
    st.markdown("---")
    st.caption("Developed with Vibe Coding")

# -----------------------------------------------------------------------------
# 4. 메인 계산 실행
# -----------------------------------------------------------------------------
if st.button("🚀 스케줄 계산하기 (Click)", type="primary", use_container_width=True):
    
    # 리드타임 설정 (필요시 수정 가능)
    LT_IN_DC = 10
    LT_SHIP = 53
    LT_HANDOVER = 7
    LT_SEWING = 35
    LT_TRANSIT = 14 if fabric_origin != sewing_origin else 5
    LT_FABRIC = 50

    # 역산 로직 시작
    schedule = []
    
    # 1. In Store -> Ship
    date_dc = target_date - timedelta(days=LT_IN_DC)
    date_ship = date_dc - timedelta(days=LT_SHIP)
    schedule.append({"단계": "매장 입고 (In Store)", "날짜": target_date, "설명": "목표일", "지연": 0})
    schedule.append({"단계": "선적 (Ex-Factory)", "날짜": date_ship, "설명": f"물류/선적 {LT_SHIP+LT_IN_DC}일", "지연": 0})

    # 2. Ship -> Cut (봉제국가 휴일 적용)
    date_handover, d1 = subtract_business_days(date_ship, LT_HANDOVER, sewing_origin)
    date_cut, d2 = subtract_business_days(date_handover, LT_SEWING, sewing_origin)
    schedule.append({"단계": "봉제 투입 (Cut Date)", "날짜": date_cut, "설명": f"봉제 {LT_SEWING}일 + 핸드오버 {LT_HANDOVER}일", "지연": d1+d2})

    # 3. Cut -> In House (운송)
    date_inhouse = date_cut - timedelta(days=LT_TRANSIT)
    schedule.append({"단계": "원단 입고 (In House)", "날짜": date_inhouse, "설명": f"운송 {LT_TRANSIT}일", "지연": 0})

    # 4. In House -> Booking (원단국가 휴일 적용)
    date_book, d3 = subtract_business_days(date_inhouse, LT_FABRIC, fabric_origin)
    schedule.append({"단계": "원단 발주 (Booking)", "날짜": date_book, "설명": f"원단생산 {LT_FABRIC}일", "지연": d3})

    # 데이터프레임 변환
    df = pd.DataFrame(schedule)
    df = df.iloc[::-1] # 시간 순서대로 정렬 (Booking -> In Store)

    # -------------------------------------------------------------------------
    # 5. 결과 화면 출력
    # -------------------------------------------------------------------------
    
    # 상단 요약 카드
    st.success(f"✅ 최종 발주 데드라인: **{date_book.strftime('%Y-%m-%d')}**")
    
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("총 리드타임", f"{(target_date - date_book).days} 일")
    col_b.metric("휴일로 인한 지연", f"{d1+d2+d3} 일", delta_color="inverse")
    col_c.metric("원단/봉제 국가", f"{fabric_origin} / {sewing_origin}")

    st.subheader("📅 상세 스케줄 (Time & Action)")
    
    # 표 스타일링
    def highlight_booking(row):
        return ['background-color: #ffcccc' if row['단계'] == "원단 발주 (Booking)" else '' for _ in row]

    st.dataframe(
        df.style.apply(highlight_booking, axis=1),
        column_config={
            "날짜": st.column_config.DateColumn("날짜", format="YYYY-MM-DD"),
            "지연": st.column_config.NumberColumn("휴일 영향(일)", format="%d일 지연 ⚠️"),
        },
        use_container_width=True,
        hide_index=True
    )

    # 엑셀 다운로드 버튼
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 스케줄 엑셀 다운로드",
        data=csv,
        file_name=f"TA_Schedule_{target_date}.csv",
        mime='text/csv',
    )
    
    if d1+d2+d3 > 5:
        st.warning(f"⚠️ 주의: 휴일로 인해 전체 일정이 {d1+d2+d3}일 밀렸습니다. 춘절/뗏 기간이 포함되었는지 확인하세요.")

else:
    st.info("👈 왼쪽 사이드바에서 날짜와 국가를 선택하고 '계산하기' 버튼을 누르세요.")
