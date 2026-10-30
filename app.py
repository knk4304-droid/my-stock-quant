import os
import pandas as pd
import streamlit as st
from backtest import run_20y_backtest

# 1. Wide 레이아웃 및 페이지 기본 설정 (화면 깨짐 방지)
st.set_page_config(
    page_title="AI 추천 주식 매매 (v4.0)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 AI 추천 주식 매매 (v4.0 초고속 캐시 개편판)")
st.caption("백그라운드 배치 연산 기반으로 800여 개 전 종목이 멈춤·누락 없이 0.01초 만에 로드됩니다.")

# 2. 로컬 Parquet 캐시 파일 불러오기 함수
@st.cache_data(ttl=3600)
def load_cached_universe():
    cache_path = "data/quant_universe_cache.parquet"
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path, engine="pyarrow")
    return pd.DataFrame()

# 캐시 데이터 로드
df_universe = load_cached_universe()

# 3. 데이터 로드 상태 및 전체 유니버스 데이터프레임 표출
if df_universe.empty:
    st.error("⚠️ 데이터 캐시 파일이 없습니다!")
    st.info("💡 터미널(CMD)에서 `python batch_update.py`를 먼저 실행하여 800여 개 종목 데이터를 생성해 주세요.")
else:
    st.success(f"✅ 캐시 데이터 로드 성공! 총 {len(df_universe)}개 종목이 완벽히 연동되었습니다.")
    
    # 상위 Top 10 퀀트 종목 표출
    st.subheader("🏆 [전체 모수 스크리닝] 통합 퀀트 스코어 Top 10")
    if "총점" in df_universe.columns:
        df_sorted = df_universe.sort_values(by="총점", ascending=False)
    else:
        df_sorted = df_universe
        
    st.dataframe(df_sorted.head(10), use_container_width=True)

    # 관심 종목 검색 및 전체 종목 조회
    with st.expander("🔍 전체 종목 목록 및 검색하기"):
        st.dataframe(df_universe, use_container_width=True)

# 4. 과거 20년 백테스팅 검증 섹션 (1단계~4단계 백테스팅 엔진 연동)
st.markdown("---")
st.header("📊 과거 20년 알고리즘 백테스팅 실증 검증")
st.write("선택한 종목에 대해 지난 20년간의 시그널 적중률, 누적 수익률(CAGR), 최대 낙폭(MDD)을 소급 적용하여 실증합니다.")

col_input, col_btn = st.columns([3, 1])
with col_input:
    # 캐시 종목이 있으면 드롭다운 제공, 없으면 텍스트 입력
    if not df_universe.empty and "종목" in df_universe.columns:
        stock_list = df_universe["종목"].tolist()
        selected_stock = st.selectbox("검증할 종목을 선택하세요", stock_list)
    else:
        selected_stock = st.text_input("검증할 티커 입력 (예: AAPL, 005930.KS)", "AAPL")

with col_btn:
    st.write("") # 높이 맞춤용 공백
    st.write("")
    run_btn = st.button("20년 백테스팅 실행", type="primary")

if run_btn:
    if selected_stock:
        with st.spinner(f"'{selected_stock}' 종목의 과거 20년 주가 데이터 분석 중..."):
            res = run_20y_backtest(selected_stock)
            
            if res:
                m1, m2, m3 = st.columns(3)
                m1.metric("20년 누적 수익률", f"{res['Total_Return']:.1f}%")
                m2.metric("최대 낙폭 (MDD)", f"{res['MDD']:.1f}%")
                m3.metric("과거 매매 승률", f"{res['Win_Rate']:.1f}%")
                
                st.subheader("📈 20년 누적 수익률 추이 그래프")
                st.line_chart(res["History_DF"])
            else:
                st.error("해당 종목의 과거 데이터를 가져오는 중 오류가 발생했습니다. 티커명을 확인해 주세요.")
    else:
        st.warning("종목을 먼저 선택해 주세요.")
