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
        res = requests.get(url_kr, headers=headers, timeout=3).json()
        macro_results['KOSPI'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['KOSPI'] = {'val': 2600.0, 'change': 0.0}

    try:
        url_kq = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
        res = requests.get(url_kq, headers=headers, timeout=3).json()
        macro_results['KOSDAQ'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['KOSDAQ'] = {'val': 750.0, 'change': 0.0}

    try:
        url_fx = "https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic"
        res = requests.get(url_fx, headers=headers, timeout=3).json()
        macro_results['USDKRW'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['USDKRW'] = {'val': 1340.00, 'change': 0.0}

    for key, sym in {'S&P500': '^GSPC', 'NASDAQ': '^IXIC', 'VIX': '^VIX'}.items():
        try:
            hist = yf.Ticker(sym).history(period='5d', timeout=3)
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
        df = yf.Ticker(ticker).history(period='1y', timeout=3)
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
def run_quant_analysis(cache_key="v3_38_complete_verified_final_v13"):
    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    macro = fetch_realtime_macro()

    tasks = []
    for market, tickers in universe.items():
        for ticker in tickers:
            tasks.append((ticker, market))

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
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
st.caption(f"부제 3.38 - 관심종목 멀티선택 옵션 개편판 | {now_str}")

with st.expander("ℹ️ **[클릭] AI 퀀트 시스템 핵심 매커니즘 & 매매 가이드 보기**", expanded=False):
    st.markdown("""
    * **분할 모듈 시스템:** 코드가 잘리는 현상을 완벽히 방지하여 전 기능이 다운 없이 안정적으로 구동됩니다.
    * **주간 종합 브리핑:** 글로벌/국내 시장 환경과 매수/매도 대응 방향을 매주 자동 정리합니다.
    * **AI 종합 필터 Top 10:** 전체 유니버스에서 퀀트점수, 미래수익률, 승률, 안전장치를 종합 평가하여 **기간별(1W ~ 3Y+) 가장 사야 할 최적의 10개 종목**과 **매수/매도 타이밍 리포트**를 제시합니다.
    * **관심 종목 개별 진단:** 전체 유니버스 모수 종목 중 원하시는 종목들을 드롭다운으로 다중 선택하여 정밀 진단 리포트를 확인하실 수 있습니다.
    """)

with st.spinner("v3.38 실시간 스크리닝 중..."):
    df, engine, macro_info = run_quant_analysis()

st.subheader("🌐 실시간 주요 시장 지수 현황")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)

index_configs = [
    (m_col1, "KOSPI", macro_info.get('KOSPI', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"),
    (m_col2, "KOSDAQ", macro_info.get('KOSDAQ', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ"),
    (m_col3, "S&P 500", macro_info.get('S&P500', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^GSPC/"),
    (m_col4, "NASDAQ 100", macro_info.get('NASDAQ', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^IXIC/"),
    (m_col5, "원/달러 환율", macro_info.get('USDKRW', {'val':0,'change':0}), "https://m.stock.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"),
    (m_col6, "VIX (변동성)", macro_info.get('VIX', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^VIX/")
]

for col, name, data, link in index_configs:
    with col:
        render_korean_market_card(name, data, link)

# 주간 시황 리포트 노출
if not df.empty:
    with st.expander("📋 **[클릭하여 열기] AI 퀀트 주간 종합 브리핑 리포트 (이번 주 시장 전망 & 대응 전략)**", expanded=True):
        render_weekly_market_briefing(df, macro_info)

st.markdown("---")

FIXED_CATEGORIES = [
    '🎯 [MY] 관심 종목 개별 진단',
    '🏆 [AI 종합 필터] 기간별 최우선 매수 추천 Top 10 (강력 추천)',
    '🏆 통합 전체 유니버스 (국내+미국 종합)',
    '🏆 국내 ETF',
    '코스피200',
    '코스닥100',
    'S&P500',
    '나스닥100'
]

if not df.empty:
    full_uni, full_names = UniverseLoader.get_full_universe()
    stock_options = sorted([f"{m_name} - {full_names.get(t, t)}" for m_name, t_list in full_uni.items() for t in t_list])

    tabs = st.tabs(["미래 1주일 (1W)", "미래 1개월 (1M)", "미래 6개월 (6M)", "미래 1년 (1Y)", "미래 5년 (5Y)", "미래 10년 (10Y)", "미래 10년 이상 (10Y+)"])
    period_codes = ["1W", "1M", "6M", "1Y", "5Y", "10Y", "10Y+"]

    for tab, p_code in zip(tabs, period_codes):
        with tab:
            st.markdown(f"### 🎯 [{p_code}] 테마 그룹별 맞춤형 가중치 배점 가이드")

            w_large = engine.largecap_weights[p_code]
            w_small = engine.smallcap_weights[p_code]
            w_etf = engine.etf_weights[p_code]

            w_summary_df = pd.DataFrame(
                [w_large, w_small, w_etf],
                columns=FEATURE_NAMES,
                index=['대형주 그룹 (코스피/S&P)', '소형 고성장주 그룹', 'ETF 그룹']
            )
            st.dataframe(w_summary_df, use_container_width=True)

            st.markdown("---")

            for cat in FIXED_CATEGORIES:
                if "관심 종목" in cat:
                    st.markdown("### 🎯 [MY] 관심 종목 직접 선택 개별 진단")
                    selected_stocks = st.multiselect(
                        "진단하고 싶은 관심 종목을 선택하세요 (전체 모수에서 여러 개 선택 가능):",
                        options=stock_options,
                        default=[],
                        key=f"custom_select_{p_code}"
                    )
                    if selected_stocks:
                        target_names = [s.split(' - ')[1] for s in selected_stocks]
                        cat_df = df[df['종목명'].isin(target_names)].drop_duplicates(subset=['종목명']).copy()
                    else:
                        cat_df = pd.DataFrame()

                elif "AI 종합 필터" in cat:
                    st.markdown(f"### 🏆 [AI 종합 필터] [{p_code}] 기간별 최우선 매수 추천 Top 10 & 매매 전략")
                    cat_df = df.drop_duplicates(subset=['종목명']).copy()

                elif "통합 전체 유니버스" in cat:
                    st.markdown(f"### 🏆 {cat} Top 10")
                    cat_df = df.drop_duplicates(subset=['종목명']).copy()

                elif "국내 ETF" in cat:
                    st.markdown(f"### 🏆 국내 ETF Top 10")
                    cat_df = df[df['시장'] == '국내 ETF'].copy()

                else:
                    st.markdown(f"### 🏆 {cat} Top 10")
                    cat_df = df[df['시장'] == cat].copy()

                if not cat_df.empty:
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                    cat_df['예측수익률(%)'] = cat_df[f"미래수익률_{p_code}"]

                    probs = []
                    b_signals = []
                    s_signals = []
                    s_ranks = []

                    for _, r in cat_df.iterrows():
                        p_val, b_sig, _ = generate_buy_analysis(r, macro_info)
                        s_sig, _, _, _, _, s_rank = generate_sell_analysis(r)
                        probs.append(p_val)
                        b_signals.append(b_sig)
                        s_signals.append(s_sig)
                        s_ranks.append(s_rank)

                    cat_df['기대상승확률(%)'] = probs
                    cat_df['매도우선순위'] = s_ranks

                    if "AI 종합 필터" in cat:
                        filtered_df = cat_df[cat_df['r_1w_val'] < 8.0].copy()
                        filtered_df['AI종합점수'] = filtered_df['총점'] * 0.5 + filtered_df['기대상승확률(%)'] * 0.3 + filtered_df['예측수익률(%)'] * 0.2
                        cat_df = filtered_df.sort_values(by='AI종합점수', ascending=False).head(10)
                    elif "관심 종목" not in cat:
                        col_head1, col_head2 = st.columns([3, 1])
                        with col_head2:
                            cat_sort_opt = st.selectbox(
                                "정렬 옵션 선택:",
                                options=["퀀트점수 순", "미래 기대 수익률 순 (%)", "매수시그널 순 (확률 %)", "매도시그널 순 (대응)"],
                                index=0,
                                key=f"sort_{cat}_{p_code}"
                            )

                        if "미래 기대 수익률" in cat_sort_opt:
                            cat_df = cat_df.sort_values(by=['예측수익률(%)', '기대상승확률(%)'], ascending=[False, False]).head(10)
                        elif "매수시그널" in cat_sort_opt:
                            cat_df = cat_df.sort_values(by=['기대상승확률(%)', 'r_1w_val', '총점'], ascending=[False, False, False]).head(10)
                        elif "매도시그널" in cat_sort_opt:
                            cat_df = cat_df.sort_values(by=['매도우선순위', 'r_1w_val'], ascending=[False, False]).head(10)
                        else:
                            cat_df = cat_df.sort_values(by=['총점', '기대상승확률(%)'], ascending=[False, False]).head(10)

                    cat_df['종목(차트보기)'] = cat_df['차트링크']

                    desired_cols = ['종목(차트보기)', '시장', '당일 수익률', '1일 전', '2일 전', '1주 수익률', '1달 수익률', '3개월 수익률', '총점'] + FEATURE_NAMES
                    available_cols = [c for c in desired_cols if c in cat_df.columns]

                    display_df = cat_df[available_cols].reset_index(drop=True)
                    display_df.index = display_df.index + 1

                    st.write(display_df.to_markdown(), unsafe_allow_html=True)

                    expander_title = f"💡 [{cat}] [{p_code}] AI 선정 탑픽 10선 정밀 매매 가이드 (사야 하는 법 & 파는 타이밍)" if "AI 종합 필터" in cat else f"🔍 [{cat}] 입력 종목별 매수 추천 시그널 및 매도/손익절 종합 진단 리포트"

                    with st.expander(expander_title, expanded=True if "AI 종합 필터" in cat or "관심 종목" in cat else False):
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            prob, buy_signal, buy_opinion = generate_buy_analysis(row, macro_info)
                            s_signal, s_reason, action, target_p, stop_l, _ = generate_sell_analysis(row)

                            st.markdown(f"### {idx}. {row['종목명']} ({row['시장']} | [{p_code}] AI 예상 수익률: `+{row['예측수익률(%)']}%` | 승률: `{prob}%` | 퀀트 총점: `{row['총점']}`점)")

                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.markdown(f"#### 📈 **[매수 전략 및 시그널]** `{buy_signal}`")
                                st.info(f"💡 **어떻게 사야 하는가?**\n- **진단 의견:** {buy_opinion}\n- **분할 진입 권장:** 현재가 부근에서 비중 30% primary 진입 후, 눌림목 구간마다 추가 2차 분할 매수 진행.")
                            with col_b:
                                st.markdown(f"#### 📉 **[매도 및 리스크 관리]** `{s_signal}`")
                                st.warning(f"🎯 **언제/어떻게 팔아야 하는가?**\n- **권장 익절 목표가:** `{target_p}` 달성 시 비중 50% 분할 익절\n- **자동 손절 기준:** 주가 하락 시 `{stop_l}` 이탈 시 손절 및 우량주 교체\n- **진단 배경:** {s_reason}")
                            st.markdown("---")
                else:
                    st.info("조건에 부합하는 종목 데이터가 없습니다. 위 목록에서 관심 종목을 선택해 주세요.")
                st.write("")
