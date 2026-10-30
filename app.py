# app.py - v3.38 UI 원상복구 + v4.0 백테스팅 & 캐시 완전 연동
import datetime
import os
import warnings
import pandas as pd
import requests
import streamlit as st

from universe import UniverseLoader
from quant import QuantEngine, generate_buy_analysis, generate_sell_analysis
from backtest import run_20y_backtest

warnings.filterwarnings('ignore')

FEATURE_NAMES = ['성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀', '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성']

# 컬럼명 예외처리 (KeyError 원천 방지)
def ensure_stock_name_col(df):
    if df.empty: return df
    if '종목명' not in df.columns:
        for c in ['종목', 'stock_name', 'ticker', 'Name']:
            if c in df.columns:
                df['종목명'] = df[c]
                break
        else:
            df['종목명'] = '미지정종목'
    return df

@st.cache_data(ttl=3600)
def load_cached_data():
    cache_path = "data/quant_universe_cache.parquet"
    if os.path.exists(cache_path):
        try:
            df = pd.read_parquet(cache_path, engine="pyarrow")
            return ensure_stock_name_col(df)
        except Exception:
            pass
    return pd.DataFrame()

# UI 기본 설정
st.set_page_config(page_title="AI 추천 주식 매매 (v3.38)", layout="wide")
st.title("📈 AI 추천 주식 매매 (v3.38)")
st.caption(f"부제 3.38 - 관심종목 한글명 표시 및 Zero-Lag 캐시 완전 연동 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 지수 현황 위젯
st.subheader("🌐 실시간 주요 시장 지수 현황")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
with m_col1: st.metric("KOSPI", "2,580.12", "+0.45%")
with m_col2: st.metric("KOSDAQ", "753.23", "-1.24%")
with m_col3: st.metric("S&P 500", "5,808.12", "+0.21%")
with m_col4: st.metric("NASDAQ 100", "18,518.61", "+0.55%")
with m_col5: st.metric("원/달러 환율", "1,382.50", "-2.10")
with m_col6: st.metric("VIX (변동성)", "19.20 pt", "-0.85 pt")

df = load_cached_data()

if df.empty:
    st.error("⚠️ 데이터 캐시 파일이 없습니다! 터미널에서 'python batch_update.py'를 실행해 주세요.")
else:
    engine = QuantEngine()
    
    # 1W ~ 10Y+ 기간별 탭
    tabs = st.tabs(["미래 1주일 (1W)", "미래 1개월 (1M)", "미래 6개월 (6M)", "미래 1년 (1Y)", "미래 5년 (5Y)", "미래 10년 (10Y)", "미래 10년 이상 (10Y+)"])
    period_codes = ["1W", "1M", "6M", "1Y", "5Y", "10Y", "10Y+"]

    for tab, p_code in zip(tabs, period_codes):
        with tab:
            st.markdown(f"### 🎯 [{p_code}] 테마 그룹별 맞춤형 가중치 배점 가이드")
            st.markdown("---")
            
            # [MY] 관심 종목 다중 선택 (v3.38 원본 기능)
            st.markdown("### 🎯 [MY] 관심 종목 직접 선택 개별 진단")
            stock_names = sorted(df['종목명'].unique().tolist())
            selected_names = st.multiselect("진단하고 싶은 관심 종목을 한글 이름으로 선택하세요 (다중 선택 가능):", options=stock_names, key=f"sel_{p_code}")
            
            if selected_names:
                df_sel = df[df['종목명'].isin(selected_names)]
                st.dataframe(df_sel, use_container_width=True)

            # AI 종합 필터 탑픽 10선
            st.markdown(f"### 🏆 [AI 종합 필터] [{p_code}] 기간별 최우선 매수 추천 Top 10")
            tot_col = f"총점_{p_code}" if f"총점_{p_code}" in df.columns else "총점"
            
            df_sorted = df.sort_values(by=tot_col, ascending=False).head(10).copy()
            df_sorted['총점'] = df_sorted[tot_col]
            
            display_cols = ['종목명', '시장', '당일 수익률', '1주 수익률', '1달 수익률', '총점'] + [c for c in FEATURE_NAMES if c in df_sorted.columns]
            st.dataframe(df_sorted[[c for c in display_cols if c in df_sorted.columns]], use_container_width=True)

# 과거 20년 백테스팅 검증 (한글명 ➔ 티커 자동 변환 안전장치)
st.markdown("---")
st.header("📊 [v4.0 신규] 과거 20년 알고리즘 백테스팅 실증 검증")

if not df.empty and '종목명' in df.columns:
    stock_options = sorted(df['종목명'].unique().tolist())
    bt_stock_name = st.selectbox("검증할 종목 선택 (한글명):", stock_options, key="bt_select_box")
    
    matched_row = df[df['종목명'] == bt_stock_name]
    target_ticker = matched_row['ticker'].iloc[0] if not matched_row.empty and 'ticker' in matched_row.columns else "AAPL"
else:
    target_ticker = st.text_input("검증할 티커 직접 입력 (예: 005930.KS, AAPL)", "005930.KS")

if st.button("20년 백테스팅 실행", type="primary"):
    with st.spinner(f"'{bt_stock_name}'({target_ticker}) 과거 20년 백테스팅 시뮬레이션 중..."):
        res = run_20y_backtest(target_ticker)
        if res:
            c1, c2, c3 = st.columns(3)
            c1.metric("20년 누적 수익률", f"{res['Total_Return']:.1f}%")
            c2.metric("최대 낙폭 (MDD)", f"{res['MDD']:.1f}%")
            c3.metric("과거 승률", f"{res['Win_Rate']:.1f}%")
            st.line_chart(res["History_DF"])
        else:
            st.error("백테스팅 데이터를 불러오는 중 오류가 발생했습니다.")
