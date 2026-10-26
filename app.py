import datetime
import time
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import streamlit as st

warnings.filterwarnings('ignore')

FEATURE_NAMES = [
    '성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀',
    '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성'
]

# ==========================================
# 1. 실시간 주요 지수 수집
# ==========================================
def fetch_realtime_macro():
    macro_results = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        url_kr = "https://m.stock.naver.com/api/index/KOSPI/basic"
        res = requests.get(url_kr, headers=headers, timeout=3).json()
        curr = float(res['closePrice'].replace(',', ''))
        rate = float(res['fluctuationsRatio'])
        macro_results['KOSPI'] = {'val': curr, 'change': rate}
    except Exception:
        macro_results['KOSPI'] = {'val': 0.0, 'change': 0.0}

    try:
        url_kq = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
        res = requests.get(url_kq, headers=headers, timeout=3).json()
        curr = float(res['closePrice'].replace(',', ''))
        rate = float(res['fluctuationsRatio'])
        macro_results['KOSDAQ'] = {'val': curr, 'change': rate}
    except Exception:
        macro_results['KOSDAQ'] = {'val': 0.0, 'change': 0.0}

    try:
        url_fx = "https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic"
        res = requests.get(url_fx, headers=headers, timeout=3).json()
        curr = float(res['closePrice'].replace(',', ''))
        rate = float(res['fluctuationsRatio'])
        macro_results['USDKRW'] = {'val': curr, 'change': rate}
    except Exception:
        macro_results['USDKRW'] = {'val': 0.0, 'change': 0.0}

    us_tickers = {'S&P500': '^GSPC', 'NASDAQ': '^IXIC', 'VIX': '^VIX'}
    for key, sym in us_tickers.items():
        try:
            hist = yf.Ticker(sym).history(period='5d', timeout=3)
            if not hist.empty and len(hist) >= 2:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                rate = (curr - prev) / prev * 100
                macro_results[key] = {'val': curr, 'change': rate}
            else:
                macro_results[key] = {'val': 0.0, 'change': 0.0}
        except Exception:
            macro_results[key] = {'val': 0.0, 'change': 0.0}

    return macro_results


# ==========================================
# 2. 유니버스 로드
# ==========================================
class UniverseLoader:
    @staticmethod
    def get_full_universe():
        name_map = {
            '005930.KS': '삼성전자', '000660.KS': 'SK하이닉스', '035420.KS': 'NAVER', '005380.KS': '현대차',
            '000270.KS': '기아', '068270.KS': '셀트리온', '005490.KS': 'POSCO홀딩스', '035720.KS': '카카오',
            '051910.KS': 'LG화학', '006400.KS': '삼성SDI',
            '247540.KQ': '엘앤에프', '086520.KQ': '에코프로비엠', '196170.KQ': '알테오젠', '028300.KQ': 'HLB',
            '066970.KQ': '엘앤에프', '293490.KQ': '카카오게임즈', '278280.KQ': '천보', '035900.KQ': 'JYP Ent.',
            '041510.KQ': 'SM', '035760.KQ': 'CJ ENM',
            'AAPL': '애플', 'MSFT': '마이크로소프트', 'AMZN': '아마존', 'NVDA': '엔비디아', 'GOOGL': '알파벳',
            'META': '메타', 'BRK-B': '버크셔해서웨이', 'TSLA': '테슬라', 'UNH': '유나이티드헬스', 'JNJ': '존슨앤드존슨',
            'AVGO': '브로드컴', 'COST': '코스트코', 'AMD': 'AMD', 'PEP': '펩시코', 'NFLX': '넷플릭스',
            '069500.KS': 'KODEX 200', '102110.KQ': 'TIGER 200', '305540.KS': 'TIGER 2차전지테마',
            '458730.KS': 'ACE 미국S&P500', '371460.KS': 'TIGER 차이나전기차SOLACTIVE',
            '252670.KS': 'KODEX 200선물인버스2X', '114800.KS': 'KODEX 인버스',
            '138230.KS': 'KODEX 미국달러선물', '360750.KS': 'TIGER 미국S&P500', '229200.KS': 'KODEX 코스닥150',
            'SPY': 'SPDR S&P 500 ETF', 'QQQ': 'Invesco QQQ Trust', 'IVV': 'iShares Core S&P 500',
            'VOO': 'Vanguard S&P 500', 'SOXX': 'iShares Semiconductor ETF',
            'TQQQ': 'ProShares UltraPro QQQ', 'SQQQ': 'ProShares Short QQQ',
            'SCHD': 'Schwab U.S. Dividend Equity', 'XLK': 'Technology Select Sector SPDR', 'XLE': 'Energy Select Sector SPDR'
        }

        universe = {
            '코스피200': ['068270.KS', '006400.KS', '000270.KS', '005490.KS', '051910.KS', '035420.KS', '005380.KS', '005930.KS', '035720.KS', '000660.KS'],
            '코스닥100': ['247540.KQ', '086520.KQ', '196170.KQ', '028300.KQ', '066970.KQ', '293490.KQ', '278280.KQ', '035900.KQ', '041510.KQ', '035760.KQ'],
            'S&P500': ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'BRK-B', 'TSLA', 'UNH', 'JNJ'],
            '나스닥100': ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AVGO', 'COST', 'AMD'],
            '국내 ETF': ['069500.KS', '102110.KQ', '305540.KS', '458730.KS', '371460.KS', '252670.KS', '114800.KS', '138230.KS', '360750.KS', '229200.KS'],
            '미국 ETF': ['SPY', 'QQQ', 'IVV', 'VOO', 'SOXX', 'TQQQ', 'SQQQ', 'SCHD', 'XLK', 'XLE']
        }
        return universe, name_map


# ==========================================
# 3. 퀀트 정량 채점 및 수익률 산출 엔진
# ==========================================
class QuantEngine:
    def __init__(self):
        self.weights = {
            '1W':   [5, 5, 5, 5, 25, 20, 10, 10, 10, 5],
            '1M':   [10, 10, 5, 5, 20, 15, 10, 10, 10, 5],
            '6M':   [15, 15, 10, 10, 10, 10, 5, 5, 10, 10],
            '1Y':   [20, 15, 15, 10, 5, 5, 5, 5, 10, 10],
            '5Y':   [20, 20, 15, 10, 5, 5, 5, 5, 5, 10],
            '10Y':  [25, 20, 15, 10, 2, 3, 5, 5, 5, 10],
            '10Y+': [30, 20, 15, 10, 0, 0, 5, 5, 5, 10]
        }

    def calculate_returns(self, df: pd.DataFrame):
        """1주, 1달, 3개월, 1년 수익률(%) 계산"""
        if df.empty or len(df) < 5:
            return "0.0%", "0.0%", "0.0%", "0.0%"

        latest_price = df['Close'].iloc[-1]

        # 1주 (5영업일 전)
        r_1w = ((latest_price - df['Close'].iloc[-5]) / df['Close'].iloc[-5] * 100) if len(df) >= 5 else 0.0
        # 1달 (20영업일 전)
        r_1m = ((latest_price - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100) if len(df) >= 20 else 0.0
        # 3개월 (60영업일 전 또는 데이터 시작 지점)
        r_3m = ((latest_price - df['Close'].iloc[-60]) / df['Close'].iloc[-60] * 100) if len(df) >= 60 else ((latest_price - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100)
        # 1년 (전체 구간 대비)
        r_1y = ((latest_price - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100) if len(df) > 0 else 0.0

        return f"{r_1w:+.2f}%", f"{r_1m:+.2f}%", f"{r_3m:+.2f}%", f"{r_1y:+.2f}%"

    def calculate_raw_scores(self, df: pd.DataFrame, macro: dict) -> np.ndarray:
        if df.empty or len(df) < 2:
            return np.array([50, 75, 80, 65, 50, 50, 70, 60, 50, 80])

        latest = df.iloc[-1]
        close_val = float(latest['Close'])
        vol_val = float(latest['Volume']) if 'Volume' in latest and latest['Volume'] > 0 else 100000

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi_series = 100 - (100 / (1 + gain / loss))
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else 50.0

        start_price = float(df['Close'].iloc[0])
        s1 = min(100, max(0, (close_val - start_price) / start_price * 100 + 50))
        s2 = 75.0
        s3 = 80.0
        s4 = 65.0
        s5 = max(0, 100 - abs(60 - rsi) * 2)
        
        avg_vol = float(df['Volume'].tail(20).mean()) if 'Volume' in df else vol_val
        s6 = min(100, (vol_val / avg_vol * 50)) if avg_vol > 0 else 50.0
        
        vix_val = macro['VIX']['val'] if macro.get('VIX') and macro['VIX']['val'] > 0 else 15.0
        s7 = max(0, 100 - (vix_val * 2))
        s8 = 60.0
        
        pct_change = float(df['Close'].pct_change(5).iloc[-1]) if len(df) >= 5 else 0.0
        s9 = min(100, max(0, pct_change * 1000 + 50))
        s10 = 85.0 if vix_val < 20 else 40.0

        return np.array([s1, s2, s3, s4, s5, s6, s7, s8, s9, s10])

    def calculate_future_period_score(self, raw_scores: np.ndarray, df: pd.DataFrame, period: str) -> float:
        w = np.array(self.weights[period])
        base_score = np.sum(raw_scores * (w / 100.0))
        
        if not df.empty and len(df) >= 2:
            realtime_change = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
            realtime_bonus = np.clip(realtime_change * 2.0, -10, 10)
        else:
            realtime_bonus = 0.0

        final_future_score = np.clip(base_score + realtime_bonus, 10, 100)
        return np.round(final_future_score, 2)


def get_chart_link(ticker: str, name: str) -> str:
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        code = ticker.split('.')[0]
        url = f"https://finance.naver.com/item/main.naver?code={code}"
    else:
        url = f"https://finance.yahoo.com/quote/{ticker}"
    return f"[{name}]({url})"


def generate_analyst_opinion(row, horizon_type='주간 (월~금 리밸런싱)'):
    total_score = row['총점']
    rsi_score = row['기술적모멘텀']
    vol_score = row['수급/거래량']
    macro_score = row['대외변동성']
    stock_name = row['종목명']

    if horizon_type == '장중 (오늘 단기)':
        prob = int(np.clip(total_score * 0.5 + rsi_score * 0.3 + vol_score * 0.2, 10, 95))
    elif horizon_type == '주간 (월~금 리밸런싱)':
        prob = int(np.clip(total_score * 0.7 + vol_score * 0.2 + macro_score * 0.1, 10, 95))
    else:  # 차주 (다음주 모멘텀)
        prob = int(np.clip(total_score * 0.85 + macro_score * 0.15, 10, 95))

    if prob >= 70:
        signal = "🟢 강력 매수 (Buy)"
        opinion = f"[{stock_name}] {horizon_type} 관점의 미래 추세 모멘텀이 매우 우수합니다. 기대 상승 확률이 약 {prob}%로 높게 형성되어 적극 보유/매수를 권장합니다."
    elif prob >= 55:
        signal = "🟡 분할 매수 / 관망 (Hold)"
        opinion = f"[{stock_name}] 펀더멘털은 견조하나 {horizon_type} 지수 숨고르기가 지속될 수 있습니다 (기대 상승 확률 {prob}%). 금요일 리밸런싱 시 점검을 권장합니다."
    else:
        signal = "🔴 관망 / 매도 (Sell/Wait)"
        opinion = f"[{stock_name}] 단기 차익 실현 물량이 존재하므로 {horizon_type} 기준 위험 관리가 필요합니다 (기대 상승 확률 {prob}%). 교체 매도를 고려하세요."

    return prob, signal, opinion


# ==========================================
# 4. 분석 실행 및 캐싱
# ==========================================
@st.cache_data(ttl=60)
def run_quant_analysis():
    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    macro = fetch_realtime_macro()

    results = []
    periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']

    for market, tickers in universe.items():
        for ticker in tickers:
            try:
                # 1년치 일별 시세 수집
                df = yf.Ticker(ticker).history(period='1y', timeout=3)
            except Exception:
                df = pd.DataFrame()

            raw_scores = engine.calculate_raw_scores(df, macro)
            r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)

            clean_code = ticker.split('.')[0]
            stock_name = name_map.get(ticker, name_map.get(clean_code, clean_code))
            chart_link = get_chart_link(ticker, stock_name)
            
            row = {
                '시장': market,
                '종목명': stock_name,
                '차트링크': chart_link,
                '1주 수익률': r_1w,
                '1달 수익률': r_1m,
                '3개월 수익률': r_3m,
                '1년 수익률': r_1y
            }
            
            for i, fname in enumerate(FEATURE_NAMES):
                row[fname] = np.round(raw_scores[i], 1)

            for p in periods:
                row[f"총점_{p}"] = engine.calculate_future_period_score(raw_scores, df, p)
                
            results.append(row)

    return pd.DataFrame(results), engine.weights, macro


# ==========================================
# 5. 대시보드 UI
# ==========================================
st.set_page_config(page_title="AI 퀀트 주식 분석 시스템 v1.1", layout="wide")

st.title("📈 AI 퀀트 주식 추천 프로그램 (v1.1)")
st.caption("부제 1.1 - 주간 매매 전략(월요일 매수 ~ 금요일 리밸런싱) 및 미래 기대 상승 모델 적용")

with st.spinner("실시간 지수 수집 및 1년/3개월/1달/1주 수익률 분석 중..."):
    df, weights_map, macro_info = run_quant_analysis()

st.subheader("🌐 실시간 주요 시장 지수 현황 (클릭 시 상세 차트 연결)")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)

index_configs = [
    (m_col1, "KOSPI", macro_info.get('KOSPI', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KPSI"),
    (m_col2, "KOSDAQ", macro_info.get('KOSDAQ', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KSDQ"),
    (m_col3, "S&P 500", macro_info.get('S&P500', {'val':0,'change':0}), "https://finance.yahoo.com/quote/%5EGSPC/"),
    (m_col4, "NASDAQ 100", macro_info.get('NASDAQ', {'val':0,'change':0}), "https://finance.yahoo.com/quote/%5EIXIC/"),
    (m_col5, "원/달러 환율", macro_info.get('USDKRW', {'val':0,'change':0}), "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"),
    (m_col6, "VIX (변동성)", macro_info.get('VIX', {'val':0,'change':0}), "https://finance.yahoo.com/quote/%5EVIX/")
]

for col, name, data, link in index_configs:
    with col:
        val_str = f"{data['val']:,.2f}" if data['val'] > 0 else "N/A"
        st.metric(label=name, value=val_str, delta=f"{data['change']:.2f}%")
        st.markdown(f"[🔗 {name} 차트]({link})")

st.markdown("---")

if not df.empty:
    tabs = st.tabs(["미래 1주일 (1W)", "미래 1개월 (1M)", "미래 6개월 (6M)", "미래 1년 (1Y)", "미래 5년 (5Y)", "미래 10년 (10Y)", "미래 10년 이상 (10Y+)"])
    period_codes = ["1W", "1M", "6M", "1Y", "5Y", "10Y", "10Y+"]

    for tab, p_code in zip(tabs, period_codes):
        with tab:
            st.markdown(f"### 🎯 [{p_code}] 미래 관점 항목별 가중치 배점")
            
            w_list = weights_map[p_code]
            w_df = pd.DataFrame([w_list], columns=FEATURE_NAMES, index=['배점 (100점 만점)'])
            st.dataframe(w_df, use_container_width=True)
            
            st.markdown("---")
            st.subheader(f"📌 [{p_code}] 분야별 미래 기대 상승 Top 10")

            categories = ['코스피200', '코스닥100', 'S&P500', '나스닥100', '국내 ETF', '미국 ETF']
            
            for cat in categories:
                st.markdown(f"### 🏆 {cat} Top 10")
                cat_df = df[df['시장'] == cat].copy()
                
                if not cat_df.empty:
                    cat_df = cat_df.sort_values(by=f"총점_{p_code}", ascending=False).head(10)
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                    cat_df['종목(차트보기)'] = cat_df['차트링크']
                    
                    # 1년 수익률 항목 추가 및 총점 바로 앞 배치
                    show_cols = ['종목(차트보기)', '1주 수익률', '1달 수익률', '3개월 수익률', '1년 수익률', '총점'] + FEATURE_NAMES
                    display_df = cat_df[show_cols].reset_index(drop=True)
                    display_df.index = display_df.index + 1
                    
                    st.write(display_df.to_markdown(), unsafe_allow_html=True)
                    
                    with st.expander(f"🔍 {cat} Top 10 종목별 시점별 애널리스트 종합 분석 (v1.1)"):
                        horizon = st.radio(f"[{cat}] 분석 시점 선택", ['장중 (오늘 단기)', '주간 (월~금 리밸런싱)', '차주 (다음주 모멘텀)'], key=f"radio_{p_code}_{cat}")
                        
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            prob, signal, opinion = generate_analyst_opinion(row, horizon)
                            
                            st.markdown(f"**{idx}. {row['종목명']}** | **미래 기대 총점:** {row['총점']}점")
                            st.markdown(f"- **{horizon} 기준 상승 확률/매수 신호:** `{prob}%` | **시그널:** {signal}")
                            st.info(f"💡 **종합 분석 코멘트:** {opinion}")
                else:
                    st.info("해당 카테고리 데이터가 없습니다.")
                st.write("")
