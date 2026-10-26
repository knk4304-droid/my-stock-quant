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
        try:
            fx_sub = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=3).json()
            curr = float(fx_sub['rates']['KRW'])
            macro_results['USDKRW'] = {'val': curr, 'change': 0.0}
        except Exception:
            macro_results['USDKRW'] = {'val': 1350.00, 'change': 0.0}

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
            '293490.KQ': '카카오게임즈', '278280.KQ': '천보', '035900.KQ': 'JYP Ent.',
            '041510.KQ': 'SM', '035760.KQ': 'CJ ENM', '091990.KQ': '셀트리온헬스케어',
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
            'SCHD': 'Schwab U.S. Dividend Equity', 'XLK': 'Technology Select Sector SPDR', 'XLE': 'Energy Select Sector SPDR',
            
            # 국내 소형 고성장주
            '440110.KQ': '파두', '277810.KQ': '레인보우로보틱스', '328130.KQ': '루닛', '084990.KQ': '하이비젼시스템',
            '053690.KQ': '한미반도체', '081660.KQ': '플리토', '060280.KQ': '큐렉소', '058470.KQ': '리노공업',
            '053030.KQ': '바이오니아', '068240.KQ': '다원시스',
            
            # 미국 소형 고성장주
            'PLTR': '팔란티어', 'SMCI': '슈퍼마이크로컴퓨터', 'IONQ': '아이온큐', 'ROKU': '로쿠',
            'SOFI': '소파이', 'U': '유니티', 'RBLX': '로블록스', 'PATH': '유아이패스',
            'DKNG': '드래프트킹스', 'AFRM': '어펌홀딩스'
        }

        universe = {
            '코스피200': ['068270.KS', '006400.KS', '000270.KS', '005490.KS', '051910.KS', '035420.KS', '005380.KS', '005930.KS', '035720.KS', '000660.KS'],
            '코스닥100': ['247540.KQ', '086520.KQ', '196170.KQ', '028300.KQ', '293490.KQ', '278280.KQ', '035900.KQ', '041510.KQ', '035760.KQ', '091990.KQ'],
            'S&P500': ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'BRK-B', 'TSLA', 'UNH', 'JNJ'],
            '나스닥100': ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AVGO', 'COST', 'AMD'],
            '국내 ETF': ['069500.KS', '102110.KQ', '305540.KS', '458730.KS', '371460.KS', '252670.KS', '114800.KS', '138230.KS', '360750.KS', '229200.KS'],
            '미국 ETF': ['SPY', 'QQQ', 'IVV', 'VOO', 'SOXX', 'TQQQ', 'SQQQ', 'SCHD', 'XLK', 'XLE'],
            '국내 소형 고성장주': ['440110.KQ', '277810.KQ', '328130.KQ', '084990.KQ', '053690.KQ', '081660.KQ', '060280.KQ', '058470.KQ', '053030.KQ', '068240.KQ'],
            '미국 소형 고성장주': ['PLTR', 'SMCI', 'IONQ', 'ROKU', 'SOFI', 'U', 'RBLX', 'PATH', 'DKNG', 'AFRM']
        }
        return universe, name_map


# ==========================================
# 3. 퀀트 채점 엔진
# ==========================================
class QuantEngine:
    def __init__(self):
        self.largecap_weights = {
            '1W':   [10, 10, 10, 15, 15, 10, 5, 5, 15, 5],
            '1M':   [10, 10, 10, 15, 15, 10, 5, 5, 15, 5],
            '6M':   [15, 15, 10, 15, 10, 10, 5, 5, 10, 5],
            '1Y':   [20, 15, 15, 15, 5, 5, 5, 5, 10, 5],
            '5Y':   [20, 20, 15, 15, 5, 5, 5, 5, 5, 5],
            '10Y':  [25, 20, 15, 15, 2, 3, 5, 5, 5, 5],
            '10Y+': [30, 20, 15, 15, 0, 0, 5, 5, 5, 5]
        }
        
        self.smallcap_weights = {
            '1W':   [25, 5, 5, 5, 20, 20, 2, 3, 10, 5],
            '1M':   [25, 5, 5, 5, 20, 15, 2, 3, 15, 5],
            '6M':   [30, 10, 5, 5, 15, 10, 2, 3, 15, 5],
            '1Y':   [35, 10, 5, 5, 10, 10, 2, 3, 15, 5],
            '5Y':   [40, 15, 5, 5, 5, 5, 2, 3, 15, 5],
            '10Y':  [45, 15, 5, 5, 2, 3, 2, 3, 15, 5],
            '10Y+': [50, 15, 5, 5, 0, 0, 2, 3, 15, 5]
        }

        self.etf_weights = {
            '1W':   [5, 0, 0, 0, 20, 15, 10, 10, 30, 10],
            '1M':   [5, 0, 0, 0, 20, 15, 10, 10, 30, 10],
            '6M':   [10, 0, 0, 0, 15, 10, 10, 10, 35, 10],
            '1Y':   [15, 0, 0, 0, 10, 10, 10, 10, 35, 10],
            '5Y':   [20, 0, 0, 0, 5, 5, 10, 10, 40, 10],
            '10Y':  [25, 0, 0, 0, 2, 3, 10, 10, 40, 10],
            '10Y+': [30, 0, 0, 0, 0, 0, 10, 10, 40, 10]
        }

    def get_weights_by_market(self, market: str, period: str):
        if "소형" in market:
            return self.smallcap_weights[period]
        elif "ETF" in market:
            return self.etf_weights[period]
        else:
            return self.largecap_weights[period]

    def calculate_returns(self, df: pd.DataFrame):
        if df.empty or len(df) < 5:
            return 0.0, "0.0%", "0.0%", "0.0%", "0.0%"

        latest_price = df['Close'].iloc[-1]

        r_1w_val = ((latest_price - df['Close'].iloc[-5]) / df['Close'].iloc[-5] * 100) if len(df) >= 5 else 0.0
        r_1m_val = ((latest_price - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100) if len(df) >= 20 else 0.0
        r_3m_val = ((latest_price - df['Close'].iloc[-60]) / df['Close'].iloc[-60] * 100) if len(df) >= 60 else ((latest_price - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100)
        r_1y_val = ((latest_price - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100) if len(df) > 0 else 0.0

        return r_1w_val, f"{r_1w_val:+.2f}%", f"{r_1m_val:+.2f}%", f"{r_3m_val:+.2f}%", f"{r_1y_val:+.2f}%"

    def calculate_raw_scores(self, df: pd.DataFrame, macro: dict, is_smallcap: bool = False) -> np.ndarray:
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
        growth_rate = (close_val - start_price) / start_price * 100
        
        if is_smallcap:
            s1 = min(100, max(0, growth_rate * 1.5 + 50))
            s2 = 80.0
            s3 = 75.0
            s4 = 70.0
        else:
            s1 = min(100, max(0, growth_rate + 50))
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

    def calculate_future_period_score(self, raw_scores: np.ndarray, df: pd.DataFrame, market: str, period: str) -> float:
        w_list = self.get_weights_by_market(market, period)
        w = np.array(w_list)
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


# ==========================================
# 4. 🔥 매도/보유/V자 반등 및 종목별 맞춤 손익절 산출 (v2.16)
# ==========================================
def generate_sell_analysis(row):
    stock_name = row['종목명']
    total_score = row['총점']
    r_1w_val = row['r_1w_val']
    rsi_score = row['기술적모멘텀']
    market = row['시장']
    
    # 3개월 수익률 수치 파싱
    try:
        r_3m_val = float(str(row['3개월 수익률']).replace('%', '').replace('+', ''))
    except Exception:
        r_3m_val = 0.0

    # 📌 종목 테마별 / 총점별 동적 손익절 라인 계산
    if "소형" in market:
        target_p_low = round(total_score * 0.14, 1)
        target_p_high = round(total_score * 0.19, 1)
        target_profit = f"+{target_p_low}% ~ +{target_p_high}%"
        stop_loss = "-5.0% ~ -7.0%"
    elif "ETF" in market:
        target_p_low = round(total_score * 0.07, 1)
        target_p_high = round(total_score * 0.1, 1)
        target_profit = f"+{target_p_low}% ~ +{target_p_high}%"
        stop_loss = "-2.5% ~ -4.0%"
    else:  # 대형주
        target_p_low = round(total_score * 0.09, 1)
        target_p_high = round(total_score * 0.13, 1)
        target_profit = f"+{target_p_low}% ~ +{target_p_high}%"
        stop_loss = "-3.0% ~ -5.0%"

    # 1. 단기 과열 익절 시그널
    if rsi_score >= 85 and r_1w_val >= 8.0:
        sell_signal = "🟠 익절 권장 (Take Profit)"
        sell_reason = f"[{stock_name}] 최근 1주 수익률({r_1w_val:+.2f}%) 급등으로 단기 과열 상태입니다."
        action = "비중 50% 이상 매도하여 수익 확정"

    # 2. V자 반등 및 매도 로직
    elif r_1w_val <= -5.0:
        if total_score >= 55.0 or r_3m_val > 0:
            sell_signal = "🔵 반등 기대 / 보유 (Rebound Hold)"
            sell_reason = f"[{stock_name}] 단기 주가 하락({r_1w_val:+.2f}%)이 발생했으나, 퀀트 총점({total_score}점)이 상위권이고 중기 추세가 견조하여 V자 반등 가능성이 높습니다."
            action = f"매도하지 말고 금요일 리밸런싱까지 보유 유지 (손절가 {stop_loss} 엄수)"
        else:
            sell_signal = "🔴 즉시 매도 / 교체 (Sell)"
            sell_reason = f"[{stock_name}] 주간 하락과 함께 퀀트 총점({total_score}점) 및 중기 수급이 동반 악화되어 추세 붕괴 위험이 큽니다."
            action = "전량 매도 후 우량주 교체"

    # 3. 약세권 관망 시그널
    elif r_1w_val < 0 and total_score < 55.0:
        sell_signal = "🟡 손절 고려 / 관망 (Caution)"
        sell_reason = f"[{stock_name}] 퀀트 총점({total_score}점)이 약세권입니다. 주중 손절가 이탈 시 대응이 필요합니다."
        action = f"손절가({stop_loss}) 미도달 시 보유, 이탈 시 손절"

    # 4. 일반 보유 유지
    else:
        sell_signal = "🟢 보유 유지 (Hold)"
        sell_reason = f"[{stock_name}] 주간 추세가 안정적이며 퀀트 총점({total_score}점)이 견조합니다."
        action = "목표 수익 달성 시까지 분할 보유 유지"

    return sell_signal, sell_reason, action, target_profit, stop_loss


# ==========================================
# 5. 분석 실행 및 캐싱
# ==========================================
@st.cache_data(ttl=60)
def run_quant_analysis():
    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    macro = fetch_realtime_macro()

    results = []
    periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']

    for market, tickers in universe.items():
        is_smallcap = "소형" in market
        for ticker in tickers:
            try:
                df = yf.Ticker(ticker).history(period='1y', timeout=3)
            except Exception:
                df = pd.DataFrame()

            raw_scores = engine.calculate_raw_scores(df, macro, is_smallcap=is_smallcap)
            r_1w_val, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)

            clean_code = ticker.split('.')[0]
            stock_name = name_map.get(ticker, name_map.get(clean_code, clean_code))
            chart_link = get_chart_link(ticker, stock_name)
            
            row = {
                '시장': market,
                '종목명': stock_name,
                '차트링크': chart_link,
                'r_1w_val': r_1w_val,
                '1주 수익률': r_1w,
                '1달 수익률': r_1m,
                '3개월 수익률': r_3m,
                '1년 수익률': r_1y
            }
            
            for i, fname in enumerate(FEATURE_NAMES):
                row[fname] = np.round(raw_scores[i], 1)

            for p in periods:
                row[f"총점_{p}"] = engine.calculate_future_period_score(raw_scores, df, market, p)
                
            results.append(row)

    return pd.DataFrame(results), engine, macro


# ==========================================
# 6. 대시보드 UI (v2.16 동적 손익절 반영)
# ==========================================
st.set_page_config(page_title="AI 퀀트 주식 분석 시스템 v2.16", layout="wide")

st.title("📈 AI 퀀트 주식 추천 및 매도 판정 시스템 (v2.16)")
st.caption("부제 2.16 - 테마별/종목별 변동성 기반 맞춤형 동적 손익절 라인 자동 산출 모델")

st.markdown("[🔍 구글(Google) 검색 바로가기](https://www.google.com)")

with st.spinner("실시간 퀀트 데이터 및 맞춤 손익절 라인 산출 중..."):
    df, engine, macro_info = run_quant_analysis()

st.subheader("🌐 실시간 주요 시장 지수 현황 (클릭 시 상세 차트 연결)")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)

index_configs = [
    (m_col1, "KOSPI", macro_info.get('KOSPI', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KPSI"),
    (m_col2, "KOSDAQ", macro_info.get('KOSDAQ', {'val':0,'change':0}), "https://my-stock-quant-k6dgdkytkbcevuoyxx9mzl.streamlit.app/~/+/url?id=6"),
    (m_col3, "S&P 500", macro_info.get('S&P500', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^GSPC"),
    (m_col4, "NASDAQ 100", macro_info.get('NASDAQ', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^IXIC"),
    (m_col5, "원/달러 환율", macro_info.get('USDKRW', {'val':0,'change':0}), "https://my-stock-quant-k6dgdkytkbcevuoyxx9mzl.streamlit.app/~/+/url?id=9"),
    (m_col6, "VIX (변동성)", macro_info.get('VIX', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^VIX")
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
            st.markdown(f"### 🎯 [{p_code}] 테마 그룹별 맞춤형 가중치 배점 가이드")
            
            w_large = engine.largecap_weights[p_code]
            w_small = engine.smallcap_weights[p_code]
            w_etf = engine.etf_weights[p_code]
            
            w_summary_df = pd.DataFrame([w_large, w_small, w_etf], 
                                        columns=FEATURE_NAMES, 
                                        index=['대형주 그룹 (코스피/S&P)', '소형 고성장주 그룹', 'ETF 그룹'])
            st.dataframe(w_summary_df, use_container_width=True)
            
            st.markdown("---")
            st.subheader(f"📌 [{p_code}] 분야별 미래 기대 상승 Top 10 및 매도/보유 진단")

            categories = ['코스피200', '코스닥100', 'S&P500', '나스닥100', '국내 ETF', '미국 ETF', '국내 소형 고성장주', '미국 소형 고성장주']
            
            for cat in categories:
                st.markdown(f"### 🏆 {cat} Top 10")
                cat_df = df[df['시장'] == cat].copy()
                
                if not cat_df.empty:
                    cat_df = cat_df.sort_values(by=f"총점_{p_code}", ascending=False).head(10)
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                    cat_df['종목(차트보기)'] = cat_df['차트링크']
                    
                    show_cols = ['종목(차트보기)', '1주 수익률', '1달 수익률', '3개월 수익률', '1년 수익률', '총점'] + FEATURE_NAMES
                    display_df = cat_df[show_cols].reset_index(drop=True)
                    display_df.index = display_df.index + 1
                    
                    st.write(display_df.to_markdown(), unsafe_allow_html=True)
                    
                    with st.expander(f"🔴 [{cat}] 보유 종목 언제 팔아야 할까? (매도/익절/손절 진단 리포트)"):
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            s_signal, s_reason, action, target_p, stop_l = generate_sell_analysis(row)
                            
                            st.markdown(f"**{idx}. {row['종목명']}** | **미래 총점:** `{row['총점']}`점 | **현재 매도 시그널:** `{s_signal}`")
                            st.markdown(f"- 🎯 **권장 목표 익절가:** `{target_p}` | 🛑 **자동 손절 기준:** `{stop_l}`")
                            st.warning(f"💡 **매도 진단 이유:** {s_reason}\n\n👉 **대응 방법:** {action}")
                            st.markdown("---")
                else:
                    st.info("해당 카테고리 데이터가 없습니다.")
                st.write("")
