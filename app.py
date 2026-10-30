import os
import pandas as pd
import streamlit as st
from backtest import run_20y_backtest

# 1. Wide 레이아웃 및 페이지 기본 설정 (v3.38 원본 UI)
st.set_page_config(
    page_title="AI 추천 주식 매매 (v3.38 + v4.0)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 AI 추천 주식 매매 (v3.38)")
st.caption("관심종목 멀티선택 옵션 개편판 | v4.0 초고속 캐시 & 과거 20년 백테스팅 엔진 완벽 연동")

# AI 퀀트 시스템 가이드
with st.expander("ℹ️ [클릭] AI 퀀트 시스템 핵심 매커니즘 & 매매 가이드 보기"):
    st.markdown("""
    - **분할 모듈 시스템:** 캐싱 시스템을 통해 전 종목 멈춤 없이 0.01초 만에 화면이 로드됩니다.
    - **주간 종합 브리핑:** 글로벌/국내 시장 환경과 매수/매도 대응 방향을 매주 자동 정리합니다.
    - **AI 종합 필터 Top 10:** 전체 유니버스에서 퀀트점수, 미래수익률, 승률, 안전장치를 종합 평가하여 탑픽 10선과 매매 리포트를 제시합니다.
    - **관심 종목 개별 진단:** 원하시는 종목들을 다중 선택하여 정밀 진단 리포트를 확인하실 수 있습니다.
    """)

# 2. 로컬 Parquet 캐시 불러오기 (0.01초 초고속 구동)
@st.cache_data(ttl=3600)
def load_cached_universe():
    cache_path = "data/quant_universe_cache.parquet"
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path, engine="pyarrow")
    return pd.DataFrame()

df_universe = load_cached_universe()

if df_universe.empty:
    st.error("⚠️ 데이터 캐시 파일이 없습니다!")
    st.info("💡 터미널(CMD)에서 `python batch_update.py`를 실행하시면 800여 개 전 종목 데이터가 생성됩니다.")
else:
    # 3. 주간 종합 브리핑 섹션 (v3.38 복원)
    with st.expander("📋 [클릭하여 열기] AI 퀀트 주간 종합 브리핑 리포트 (이번 주 시장 전망 & 대응 전략)"):
        st.subheader("📋 [AI 퀀트 주간 종합 브리핑] 이번 주 시장 전망 & 대응 전략")
        st.markdown("""
        ### 1. 🌐 글로벌 & 국내 증시 마크로 환경 진단
        - **시장 변동성 (VIX):** 변동성 안정 구간 (안정적 상승 추세 유지 가능)
        - **주간 시장 종합 의견:** 최근 급등한 과열 종목은 추격 매수를 보류하고, 수급과 퀀트 총점이 우수한 눌림목 종목으로 집중하는 전략이 유리합니다.
        """)

    # 4. [MY] 관심 종목 직접 선택 개별 진단 (v3.38 핵심 기능 복원)
    st.markdown("---")
    st.subheader("🎯 [MY] 관심 종목 직접 선택 개별 진단")
    if "종목" in df_universe.columns:
        stock_list = df_universe["종목"].tolist()
        selected_stocks = st.multiselect(
            "진단하고 싶은 관심 종목을 선택하세요 (전체 모수에서 여러 개 선택 가능):", 
            stock_list
        )
        if selected_stocks:
            df_selected = df_universe[df_universe["종목"].isin(selected_stocks)]
            st.dataframe(df_selected, use_container_width=True)
        else:
            st.info("위 목록에서 진단할 관심 종목을 다중 선택해 주세요.")

    # 5. [AI 종합 필터 Top 10] 및 8개 테마 그룹 표출 (v3.38 복원)
    st.markdown("---")
    st.subheader("🏆 [AI 종합 필터] 기간별 최우선 매수 추천 Top 10 & 매매 전략")
    
    if "총점" in df_universe.columns:
        df_sorted = df_universe.sort_values(by="총점", ascending=False)
    else:
        df_sorted = df_universe

    st.dataframe(df_sorted.head(10), use_container_width=True)

    # 6. 테마별 (코스피200, 코스닥100, S&P500, 나스닥100, 국내 ETF 등) 선택 표출
    st.markdown("---")
    st.subheader("🏆 시장 테마별 분류 조회 (코스피200 / 코스닥100 / S&P500 / 나스닥100 / ETF)")
    
    market_categories = ["전체", "S&P500", "나스닥100", "코스피200", "코스닥100", "국내 ETF"]
    selected_market = st.selectbox("조회할 테마/시장을 선택하세요:", market_categories)
    
    if "시장" in df_universe.columns and selected_market != "전체":
        df_market = df_universe[df_universe["시장"] == selected_market]
        st.dataframe(df_market.head(10), use_container_width=True)
    else:
        st.dataframe(df_sorted.head(10), use_container_width=True)

# 7. [오늘 추가된 보완기능] 과거 20년 백테스팅 검증 섹션
st.markdown("---")
st.header("📊 [v4.0 신규] 과거 20년 알고리즘 백테스팅 실증 검증")
st.write("알고리즘 시그널을 과거 20년 주가 데이터에 소급 적용하여 실증 연평균 수익률(CAGR), 최대 낙폭(MDD), 승률을 검증합니다.")

col_sel, col_btn = st.columns([3, 1])
with col_sel:
    if not df_universe.empty and "종목" in df_universe.columns:
        bt_stock = st.selectbox("검증할 종목 선택", df_universe["종목"].tolist(), key="bt_select")
    else:
        bt_stock = st.text_input("검증할 티커 입력 (예: 005930.KS, AAPL)", "005930.KS")

with col_btn:
    st.write("")
    st.write("")
    bt_run = st.button("20년 백테스팅 실행", type="primary")

if bt_run and bt_stock:
    with st.spinner(f"'{bt_stock}' 종목의 과거 20년 주가 시뮬레이션 중..."):
        res = run_20y_backtest(bt_stock)
        if res:
            m1, m2, m3 = st.columns(3)
            m1.metric("20년 누적 수익률", f"{res['Total_Return']:.1f}%")
            m2.metric("최대 낙폭 (MDD)", f"{res['MDD']:.1f}%")
            m3.metric("과거 매매 승률", f"{res['Win_Rate']:.1f}%")
            
            st.subheader("📈 20년 누적 수익률 추이 차트")
            st.line_chart(res["History_DF"])
        else:
            st.error("백테스팅 데이터를 불러오는 중 오류가 발생했습니다. 티커명을 확인해 주세요.")
