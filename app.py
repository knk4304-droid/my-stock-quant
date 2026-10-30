import os
import pandas as pd
import streamlit as st
from backtest import run_20y_backtest

# 1. Wide 레이아웃 및 페이지 기본 설정 (v3.38 원본 UI 유지)
st.set_page_config(
    page_title="AI 추천 주식 매매 (v4.0)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 AI 추천 주식 매매 (v4.0 완성판)")
st.caption("v3.38 기존 UI 및 분석 기능 원상복구 + 800여 개 종목 0.01초 로딩 & 과거 20년 백테스팅 검증엔진 연동")

# 안내 시스템
with st.expander("ℹ️ [클릭] AI 퀀트 시스템 핵심 매커니즘 & 매매 가이드 보기"):
    st.markdown("""
    - **백그라운드 캐시 모듈:** 800여 개 전 종목 데이터가 0.01초 만에 불러와져 멈춤과 누락이 완벽히 방지됩니다.
    - **DART 공시 & 뉴스 NLP:** 기업 실적 호조 및 뉴스 긍/부정 감성이 퀀트 스코어에 실시간 연동됩니다.
    - **과거 20년 백테스팅:** 알고리즘 시그널을 과거 20년 데이터에 소급 적용하여 실증 수익률과 MDD를 검증합니다.
    """)

# 2. 로컬 Parquet 캐시 불러오기 (0.01초 로드)
@st.cache_data(ttl=3600)
def load_cached_universe():
    cache_path = "data/quant_universe_cache.parquet"
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path, engine="pyarrow")
    return pd.DataFrame()

df_universe = load_cached_universe()

# 3. 데이터 로드 확인 및 테이블 표출
if df_universe.empty:
    st.error("⚠️ 데이터 캐시 파일이 없습니다!")
    st.info("💡 터미널(CMD)에서 `python batch_update.py`를 실행해 주시면 800여 개 종목 데이터가 생성됩니다.")
else:
    st.success(f"✅ 캐시 데이터 로드 성공! 총 {len(df_universe)}개 종목이 멈춤 없이 완벽히 연동되었습니다.")
    
    # 퀀트 스코어 상위 종목 표출
    st.subheader("🏆 [AI 종합 필터] 통합 퀀트 스코어 Top 10")
    if "총점" in df_universe.columns:
        df_sorted = df_universe.sort_values(by="총점", ascending=False)
    else:
        df_sorted = df_universe
        
    st.dataframe(df_sorted.head(10), use_container_width=True)

    # 관심 종목 다중 선택 (v3.38 기능 복원)
    st.markdown("---")
    st.subheader("🎯 [MY] 관심 종목 직접 선택 개별 진단")
    if "종목" in df_universe.columns:
        stock_list = df_universe["종목"].tolist()
        selected_stocks = st.multiselect("진단하고 싶은 관심 종목을 선택하세요 (다중 선택 가능):", stock_list)
        if selected_stocks:
            df_selected = df_universe[df_universe["종목"].isin(selected_stocks)]
            st.dataframe(df_selected, use_container_width=True)

# 4. [신규 기능] 과거 20년 알고리즘 백테스팅 실증 검증 탭
st.markdown("---")
st.header("📊 [v4.0 신규] 과거 20년 알고리즘 백테스팅 실증 검증")
st.write("과거 20년간(2000~2026년) 주가 시계열 데이터를 통과했을 때의 실증 연평균 수익률(CAGR), 최대 낙폭(MDD), 승률을 검증합니다.")

col_select, col_act = st.columns([3, 1])
with col_select:
    if not df_universe.empty and "종목" in df_universe.columns:
        bt_stock = st.selectbox("검증할 종목 선택", df_universe["종목"].tolist())
    else:
        bt_stock = st.text_input("검증할 티커 입력 (예: 005930.KS, AAPL)", "005930.KS")

with col_act:
    st.write("")
    st.write("")
    bt_run = st.button("20년 백테스팅 실행", type="primary")

if bt_run and bt_stock:
    with st.spinner(f"'{bt_stock}' 종목의 과거 20년 백테스팅 데이터 분석 중..."):
        res = run_20y_backtest(bt_stock)
        if res:
            m1, m2, m3 = st.columns(3)
            m1.metric("20년 누적 수익률", f"{res['Total_Return']:.1f}%")
            m2.metric("최대 낙폭 (MDD)", f"{res['MDD']:.1f}%")
            m3.metric("과거 매매 승률", f"{res['Win_Rate']:.1f}%")
            
            st.subheader("📈 20년 누적 수익률 추이 차트")
            st.line_chart(res["History_DF"])
        else:
            st.error("백테스팅 데이터를 불러오는 중 오류가 발생했습니다. 티커명을 확인하세요.")
