# app.py - UI 및 통합 대시보드 메인
import datetime
import warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from universe import UniverseLoader
from quant import QuantEngine, generate_buy_analysis, generate_sell_analysis

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

warnings.filterwarnings('ignore')

FEATURE_NAMES = [
    '성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀',
    '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성'
]

def fetch_realtime_macro():
    macro_results = {}
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        url_kr = "https://m.stock.naver.com/api/index/KOSPI/basic"
        res = requests.get(url_kr, headers=headers, timeout=2).json()
        macro_results['KOSPI'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['KOSPI'] = {'val': 2600.0, 'change': 0.0}

    try:
        url_kq = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
        res = requests.get(url_kq, headers=headers, timeout=2).json()
        macro_results['KOSDAQ'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['KOSDAQ'] = {'val': 750.0, 'change': 0.0}

    try:
        url_fx = "https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic"
        res = requests.get(url_fx, headers=headers, timeout=2).json()
        macro_results['USDKRW'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['USDKRW'] = {'val': 1340.00, 'change': 0.0}

    for key, sym in {'S&P500': '^GSPC', 'NASDAQ': '^IXIC', 'VIX': '^VIX'}.items():
        try:
            hist = yf.Ticker(sym).history(period='5d', timeout=2)
            if not hist.empty and len(hist) >= 2:
                curr, prev = float(hist['Close'].iloc[-1]), float(hist['Close'].iloc[-2])
                macro_results[key] = {'val': curr, 'change': (curr - prev) / prev * 100}
            else:
                macro_results[key] = {'val': 0.0, 'change': 0.0}
        except Exception:
            macro_results[key] = {'val': 0.0, 'change': 0.0}

    return macro_results

def get_chart_link(ticker: str, name: str) -> str:
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        code = ticker.split('.')[0]
        url = f"https://finance.naver.com/item/main.naver?code={code}"
    else:
        clean_ticker = ticker.replace('-', '.')
        url = f"https://finance.yahoo.com/quote/{clean_ticker}/"
    return f"[{name}]({url})"

def render_weekly_market_briefing(df, macro_info):
    vix_val = macro_info.get('VIX', {}).get('val', 15.0)
    nasdaq_chg = macro_info.get('NASDAQ', {}).get('change', 0.0)
    kospi_chg = macro_info.get('KOSPI', {}).get('change', 0.0)
    usdkrw_val = macro_info.get('USDKRW', {}).get('val', 1340.0)

    buy_picks = df[df['r_1w_val'] < 8.0].drop_duplicates('종목명').sort_values(by='총점_1W', ascending=False).head(3)
    take_profits = df[df['r_1w_val'] >= 8.0].drop_duplicates('종목명').sort_values(by='r_1w_val', ascending=False).head(3)
    stop_losses = df[(df['r_1w_val'] <= -5.0) & (df['총점_1W'] < 55.0)].drop_duplicates('종목명').head(3)

    vix_status = "🟢 변동성 안정 구간 (안정적 상승 추세 유지 가능)" if vix_val < 20.0 else "🔴 변동성 경보 구간 (분할 매수 및 리스크 관리 필수)"

    st.markdown(f"""
    ### 📋 [AI 퀀트 주간 종합 브리핑] 이번 주 시장 전망 & 대응 전략
    
    #### 1. 🌐 글로벌 & 국내 증시 마크로 환경 진단
    * **시장 변동성 (VIX):** 현재 `{vix_val}`pt $\rightarrow$ **{vix_status}**
    * **미국/국내 연동성:** 나스닥(`{nasdaq_chg:+.2f}%`), KOSPI(`{kospi_chg:+.2f}%`), 원/달러 환율(`{usdkrw_val:,.2f}원`)
    * **주간 시장 종합 의견:** 단기적 차별화 장세가 강하게 나타나고 있습니다. 주가가 최근 1주일간 급등(+8% 이상)한 과열 종목은 추격 매수를 보류하고, 수급과 퀀트 총점이 우수한 눌림목 종목으로 집중하는 전략이 유리합니다.

    #### 2. 🟢 이번 주 최우선 강력 매수 관심 종목 (Top Picks)
    """)
    for idx, (_, r) in enumerate(buy_picks.iterrows(), start=1):
        st.markdown(f"    {idx}. **{r['종목명']} ({r['시장']})** | 예측 수익률: `+{r['미래수익률_1W']}%` | 퀀트 총점: `{r['총점_1W']}`점\n       👉 **매수 타점:** 현재가 부근 비중 30% 1차 진입 후 눌림목마다 분할 매수")

    st.markdown("\n    #### 🔴 이번 주 비중 축소 (익절 & 교체 매도) 리딩 종목")
    if not take_profits.empty:
        for _, r in take_profits.iterrows():
            st.markdown(f"    - 🟠 **[익절 권장] {r['종목명']}** (1주 등락률 `+{r['r_1w_val']:.1f}%` 목표가 돌파 $\rightarrow$ 보유 비중 50% 이상 분할 매도하여 수익 확정)")
    if not stop_losses.empty:
        for _, r in stop_losses.iterrows():
            st.markdown(f"    - 🔴 **[손절/교체] {r['종목명']}** (1주 등락률 `{r['r_1w_val']:.1f}%`, 퀀트 총점 `{r['총점_1W']}`점 약세 $\rightarrow$ 전량 매도 후 우량주 교체)")

def process_single_stock(ticker, market, name_map, engine, macro):
    clean_code = ticker.split('.')[0]
    stock_name = name_map.get(ticker, name_map.get(clean_code, clean_code))

    try:
        df = yf.Ticker(ticker).history(period='1y', timeout=2)
    except Exception:
        df = pd.DataFrame()

    raw_scores = engine.calculate_raw_scores(df, macro, market, stock_name)
    r_1w_val, r_today, r_1d, r_2d, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)

    try:
        r_1m_val = float(str(r_1m).replace('%', '').replace('+', ''))
    except Exception:
        r_1m_val = 0.0

    chart_link = get_chart_link(ticker, stock_name)

    row = {
        '시장': market,
        '종목명': stock_name,
        '차트링크': chart_link,
        'r_1w_val': r_1w_val,
        '당일 수익률': r_today,
        '1일 전': r_1d,
        '2일 전': r_2d,
        '1주 수익률': r_1w,
        '1달 수익률': r_1m,
        '3개월 수익률': r_3m,
        '1년 수익률': r_1y,
    }

    for i, fname in enumerate(FEATURE_NAMES):
        row[fname] = np.round(raw_scores[i], 1)

    periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']
    for p in periods:
        row[f"총점_{p}"] = engine.calculate_v3_score(raw_scores, market, p, r_1w_val, r_1m_val, macro)
        row[f"미래수익률_{p}"] = engine.calculate_pure_future_return(raw_scores, market, p, r_1w_val, r_1m_val, macro)

    return row

@st.cache_data(ttl=86400)
def run_quant_analysis(cache_key="v3_38_etf_included"):
    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    macro = fetch_realtime_macro()

    tasks = []
    for market, tickers in universe.items():
        for ticker in tickers:
            tasks.append((ticker, market))

    results = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(process_single_stock, ticker, market, name_map, engine, macro) for ticker, market in tasks]
        for future in futures:
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception:
                pass

    return pd.DataFrame(results), engine, macro

def render_korean_market_card(title, data, link):
    val = data.get('val', 0.0)
    change = data.get('change', 0.0)
    val_str = f"{val:,.2f}" if val > 0 else "N/A"

    if change > 0:
        color = "#FF3B30"
        sign = "▲ "
        change_str = f"{sign}+{change:.2f}%"
    elif change < 0:
        color = "#007AFF"
        sign = "▼ "
        change_str = f"{sign}{change:.2f}%"
    else:
        color = "#8E8E93"
        change_str = "0.00%"

    card_html = f"""
    <div style="
        background-color: #F8F9FA;
        border: 1px solid #E9ECEF;
        border-radius: 10px;
        padding: 12px 15px;
        text-align: center;
        margin-bottom: 10px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.04);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #495057; margin-bottom: 4px;">{title}</div>
        <div style="font-size: 20px; font-weight: 700; color: {color}; margin-bottom: 2px;">{val_str}</div>
        <div style="font-size: 13px; font-weight: 700; color: {color}; margin-bottom: 8px;">{change_str}</div>
        <a href="{link}" target="_blank" style="
            display: inline-block;
            font-size: 11px;
            color: #6C757D;
            text-decoration: none;
            background-color: #E9ECEF;
            padding: 3px 8px;
            border-radius: 4px;
        ">🔗 차트보기</a>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# UI 실행
st.set_page_config(page_title="AI 추천 주식 매매 (v3.38)", layout="wide")

if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=30 * 1000, key="quant_realtime_loop")

now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

st.title("📈 AI 추천 주식 매매 (v3.38)")
st.caption(f"부제 3.38 - 국내 ETF 테마 포함 완결판 | {now_str}")

with st.expander("ℹ️ **[클릭] AI 퀀트 시스템 핵심 매커니즘 & 매매 가이드 보기**", expanded=False):
    st.markdown("""
    * **분할 모듈 시스템:** 코드가 잘리는 현상을 완벽히 방지하여 전 기능이 다운 없이 안정적으로 구동됩니다.
    * **주간 종합 브리핑:** 글로벌/국내 시장 환경과 매수/매도 대응 방향을 매주 자동 정리합니다.
    * **AI 종합 필터 Top 10:** 전체 유니버스에서 퀀트점수, 미래수익률, 승률, 안전장치를 종합 평가하여 **기간별(1W ~ 3Y+) 가장 사야 할 최적의 10개 종목**과 **매수/매도 타이밍 리포트**를 제시합니다.
    * **관심 종목 개별 진단:** 궁금한 국내/미국 종목명을 직접 입력하면 퀀트 알고리즘이 분석표와 종합 진단 리포트를 작성해 드립니다.
    """)

with st.spinner("v3.38 실시간 스크리닝 중..."):
    df, engine, macro_info = run_quant_analysis()

st.subheader("🌐 실시간 주요 시장 지수 현황")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)

index_configs = [
    (m_col1, "KOSPI", macro_info.get('KOSPI', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"),
    (m_col2, "KOSDAQ", macro_info.get('KOSDAQ', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ"),
