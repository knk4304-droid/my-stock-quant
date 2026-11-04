import datetime, json, time, warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests, streamlit as st, yfinance as yf

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

warnings.filterwarnings('ignore')

# 10대 핵심 평가 요인
FEATURE_NAMES = [
    '수급/거래량', '기술적모멘텀', '시장상대강도', '뉴스NLP감성', '대외변동성',
    '성장성(CAGR)', '수익성(ROE)', '밸류에이션', '재무건전성', '환율/금리환경'
]

# ==========================================
# 1. 실시간 주요 지수 수집
# ==========================================
def fetch_realtime_macro():
    macro = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    for key, code in [('KOSPI', 'KOSPI'), ('KOSDAQ', 'KOSDAQ')]:
        try:
            url = f"https://m.stock.naver.com/api/index/{code}/basic"
            res = requests.get(url, headers=headers, timeout=3).json()
            macro[key] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
        except Exception:
            macro[key] = {'val': 0.0, 'change': 0.0}

    try:
        url_fx = "https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic"
        res = requests.get(url_fx, headers=headers, timeout=3).json()
        macro['USDKRW'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro['USDKRW'] = {'val': 1350.0, 'change': 0.0}

    for key, sym in [('S&P500', '^GSPC'), ('NASDAQ', '^IXIC'), ('VIX', '^VIX')]:
        try:
            h = yf.Ticker(sym).history(period='5d', timeout=3)
            if not h.empty and len(h) >= 2:
                curr = float(h['Close'].iloc[-1])
                prev = float(h['Close'].iloc[-2])
                macro[key] = {'val': curr, 'change': (curr - prev) / prev * 100.0}
            else:
                macro[key] = {'val': 0.0, 'change': 0.0}
        except Exception:
            macro[key] = {'val': 0.0, 'change': 0.0}
    return macro

# ==========================================
# 2. 유니버스 로드
# ==========================================
class UniverseLoader:
    @staticmethod
    def get_full_universe():
        kr_large = {'005930.KS':'삼성전자', '000660.KS':'SK하이닉스', '035420.KS':'NAVER', '005380.KS':'현대차', '000270.KS':'기아', '068270.KS':'셀트리온', '005490.KS':'POSCO홀딩스', '035720.KS':'카카오', '051910.KS':'LG화학', '006400.KS':'삼성SDI', '373220.KS':'LG에너지솔루션', '207940.KS':'삼성바이오로직스'}
        kr_small = {'196170.KQ':'알테오젠', '086520.KQ':'에코프로비엠', '028300.KQ':'HLB', '247540.KQ':'엘앤에프', '214150.KQ':'클래시스', '058470.KQ':'리노공업', '035900.KQ':'JYP Ent.', '277810.KQ':'레인보우로보틱스', '053690.KQ':'한미반도체'}
        us_large = {'AAPL':'애플', 'MSFT':'마이크로소프트', 'AMZN':'아마존', 'NVDA':'엔비디아', 'GOOGL':'알파벳', 'META':'메타', 'TSLA':'테슬라', 'BRK-B':'버크셔해서웨이', 'UNH':'유나이티드헬스', 'JNJ':'존슨앤드존슨', 'LLY':'일라이릴리', 'JPM':'JP모건체이스'}
        us_small = {'PLTR':'팔란티어', 'SMCI':'슈퍼마이크로컴퓨터', 'IONQ':'아이온큐', 'ROKU':'로쿠', 'SOFI':'소파이', 'PATH':'유아이패스'}
        etf_list = {'069500.KS':'KODEX 200', '102110.KQ':'TIGER 200', '229200.KS':'KODEX 코스닥150', '091230.KS':'TIGER 반도체', '252670.KS':'KODEX 200선물인버스2X', '114800.KS':'KODEX 인버스', '458730.KS':'ACE 미국S&P500', '133690.KS':'TIGER 미국나스닥100'}

        name_map = {**kr_large, **kr_small, **us_large, **us_small, **etf_list}
        universe = {
            '코스피200': list(kr_large.keys()),
            '코스닥100': list(kr_small.keys()),
            'S&P500': list(us_large.keys()),
            '나스닥100': list(us_large.keys())[:10],
            '국내 ETF': list(etf_list.keys()),
            '국내 소형 고성장주': list(kr_small.keys()),
            '미국 소형 고성장주': list(us_small.keys())
        }
        return universe, name_map

# ==========================================
# 3. 퀀트 채점 엔진
# ==========================================
class QuantEngine:
    def __init__(self):
        self.largecap_weights = {'1~3D': [25,25,15,10,10, 3, 3, 2, 2, 5], '1~2W': [15,20,15,15,10, 8, 7, 3, 2, 5], '1~3M': [8,10,10, 7, 5,20,15,12, 8, 5], '1Y+': [5, 5, 5, 2, 3,25,20,20,10, 5]}
        self.smallcap_weights = {'1~3D': [30,25,15,10,10, 2, 2, 1, 0, 5], '1~2W': [20,20,15,15,10, 5, 5, 2, 3, 5], '1~3M': [10,10,10, 5, 5,25,15,10, 5, 5], '1Y+': [5, 5, 5, 2, 3,30,20,15,10, 5]}
        self.etf_weights      = {'1~3D': [20,25,20, 5,10, 0, 0, 5, 5,10], '1~2W': [15,20,20,10,10, 0, 0, 5,10,10], '1~3M': [10,15,15, 5, 5,10, 5,15,10,10], '1Y+': [5, 5,10, 2, 3,20,10,20,15,10]}

    def get_weights(self, market, period):
        if "소형" in market: return self.smallcap_weights[period]
        elif "ETF" in market: return self.etf_weights[period]
        return self.largecap_weights[period]

    def calculate_returns(self, df):
        if df.empty or len(df.dropna()) < 5:
            return 0.0, "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%"
        c = df['Close'].dropna()
        lp = float(c.iloc[-1])
        r_today = ((c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] * 100.0) if len(c) >= 2 else 0.0
        r_1d = ((c.iloc[-2] - c.iloc[-3]) / c.iloc[-3] * 100.0) if len(c) >= 3 else 0.0
        r_2d = ((c.iloc[-3] - c.iloc[-4]) / c.iloc[-4] * 100.0) if len(c) >= 4 else 0.0
        r_1w = ((lp - c.iloc[-5]) / c.iloc[-5] * 100.0) if len(c) >= 5 else 0.0
        r_1m = ((lp - c.iloc[-20]) / c.iloc[-20] * 100.0) if len(c) >= 20 else 0.0
        r_3m = ((lp - c.iloc[-60]) / c.iloc[-60] * 100.0) if len(c) >= 60 else 0.0
        r_1y = ((lp - c.iloc[0]) / c.iloc[0] * 100.0) if len(c) > 0 else 0.0
        return r_1w, f"{r_today:+.2f}%", f"{r_1d:+.2f}%", f"{r_2d:+.2f}%", f"{r_1w:+.2f}%", f"{r_1m:+.2f}%", f"{r_3m:+.2f}%", f"{r_1y:+.2f}%"

    def calculate_raw_scores(self, df, macro, market, stock_name):
        if df.empty or len(df.dropna()) < 2: return np.full(10, 50.0)
        c = df['Close'].dropna()
        v = df['Volume'].dropna() if 'Volume' in df else pd.Series([100000])
        lc, start = float(c.iloc[-1]), float(c.iloc[0])
        vol_val = float(v.iloc[-1]) if not v.empty else 100000.0
        gr = (lc - start) / start * 100.0 if start > 0 else 0.0
        
        std_val = c.pct_change().dropna().std()
        volatility = float(std_val * np.sqrt(252) * 100.0) if len(c) > 5 and not np.isnan(std_val) else 20.0

        avg_v = float(v.tail(20).mean()) if not v.empty else vol_val
        s1 = np.clip((vol_val / avg_v * 50.0), 10.0, 100.0) if avg_v > 0 else 50.0
        
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi_val = 50.0
        if len(c) >= 15:
            avg_gain = float(gain.iloc[-1]) if not np.isnan(gain.iloc[-1]) else 0.0
            avg_loss = float(loss.iloc[-1]) if not np.isnan(loss.iloc[-1]) else 0.0
            if avg_loss == 0:
                rsi_val = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                rsi_val = 100.0 - (100.0 / (1.0 + rs))
        s2 = max(10.0, 100.0 - abs(60.0 - rsi_val) * 2.0)
        
        pct_change = float(c.pct_change(5).iloc[-1]) if len(c) >= 5 and not np.isnan(c.pct_change(5).iloc[-1]) else 0.0
        s3 = np.clip(pct_change * 1000.0 + 50.0, 10.0, 100.0)
        s4 = 50.0
        
        vix = macro.get('VIX', {}).get('val', 15.0)
        s5 = np.clip(75.0 - (vix - 15.0) * 3.0 - volatility * 0.3, 15.0, 85.0) if "소형" in market else np.clip(80.0 - (vix - 15.0) * 1.5, 30.0, 90.0)
        s6 = np.clip(gr + 50.0, 10.0, 100.0)
        s7 = np.clip(50.0 + gr * 0.4, 15.0, 95.0)
        ma20 = float(c.tail(20).mean()) if len(c) >= 20 else lc
        s8 = np.clip(100.0 - abs((lc / ma20) * 100.0 - 100.0) * 2.0, 15.0, 95.0) if ma20 > 0 else 50.0
        s9 = np.clip(100.0 - volatility * 1.2, 20.0, 90.0)
        s10 = np.clip(70.0 + macro.get('USDKRW', {}).get('change', 0.0) * 5.0, 30.0, 95.0)
        
        scores = np.array([s1, s2, s3, s4, s5, s6, s7, s8, s9, s10])
        return np.nan_to_num(scores, nan=50.0)

    def calculate_v3_score(self, raw, market, period, r_1w, macro):
        w = np.array(self.get_weights(market, period))
        base = np.sum(raw * (w / 100.0))
        vix_p = -5.0 if macro.get('VIX', {}).get('val', 15.0) >= 20.0 else 0.0
        return round(float(np.clip(base + vix_p, 10.0, 100.0)), 2)

    def calculate_pure_future_return(self, raw, market, period, r_1w, macro):
        if period in ['1~3D', '1~2W']:
            est = (raw[0] * 0.12) + (raw[1] * 0.08) + (r_1w * 0.25)
            return round(float(np.clip(est * 0.35 + 2.5, 1.5, 25.0)), 2)
        est = (raw[5] * 0.25) + (raw[6] * 0.20) + (raw[2] * 0.15)
        return round(float(np.clip(est * 0.8, 5.0, 150.0)), 2)

# ==========================================
# 4. 매수/매도 진단 함수
# ==========================================
def generate_buy_analysis(row, macro):
    total_score = row['총점']
    r_1w_val = row['r_1w_val']
    stock_name = row['종목명']
    tech_score = row.get('기술적모멘텀', 50.0)
    
    prob = int(np.clip(total_score + (tech_score - 50.0) * 0.2 + (r_1w_val * 0.3), 10, 95))
    if macro.get('VIX', {}).get('val', 15.0) >= 20.0:
        prob -= 5

    if r_1w_val >= 8.0:
        buy_signal = "🟠 매수 보류 (과열 오버슈팅)"
        buy_opinion = f"[{stock_name}] 최근 1주 등락률(+{r_1w_val:.1f}%) 급등으로 오버슈팅 구간입니다. 눌림목 조정을 기다리세요."
    elif prob >= 70:
        buy_signal = "🟢 강력 매수 (Buy) [70% 이상]"
        buy_opinion = f"[{stock_name}] 기대 상승 확률 약 {prob}%로 최상위 매수 시그널입니다. 분할 진입을 추천합니다."
    elif prob >= 55:
        buy_signal = "🟡 분할 매수 / 눌림목 (Hold) [55%~69%]"
        buy_opinion = f"[{stock_name}] 눌림목 및 상승 기대 구간입니다 (기대 확률 {prob}%). 1차 분할 매수 관점 진입 가능."
    else:
        buy_signal = "🔴 관망 / 매도 (Wait)"
        buy_opinion = f"[{stock_name}] 기대 상승 확률({prob}%)이 낮습니다. 신규 매수를 보류하세요."

    return prob, buy_signal, buy_opinion

def generate_sell_analysis(row):
    stock_name = row['종목명']
    total_score = row['총점']
    r_1w_val = row['r_1w_val']
    market = row['시장']

    target_profit = f"+{max(total_score*0.12, r_1w_val+2.0):.1f}% ~ +{max(total_score*0.15, r_1w_val+5.0):.1f}%"
    stop_loss = "-3.5% ~ -5.5%" if "대형" in market or "코스피" in market else "-5.0% ~ -7.5%"

    if r_1w_val >= 8.0:
        sell_signal = f"🟠 익절 권장 (Take Profit) [급등 과열: +{r_1w_val:.1f}%]"
        sell_reason = f"[{stock_name}] 주간 등락률(+{r_1w_val:.1f}%)이 오버슈팅되어 단기 상투 위험이 높습니다."
        action = "현재 구간에서 보유 비중의 50% 이상 분할 매도하여 수익을 확정하세요!"
        sell_rank_score = 100
    elif r_1w_val <= -5.0:
        if total_score >= 55.0:
            sell_signal = "🔵 반등 기대 / 보유 (Rebound Hold)"
            sell_reason = f"[{stock_name}] 단기 하락({r_1w_val:.1f}%) 중이나 퀀트 체력({total_score}점)이 우수합니다."
            action = f"V자 반등 가능성이 높으니 손절가({stop_loss}) 엄수 하에 보유 유지를 권장합니다."
            sell_rank_score = 60
        else:
            sell_signal = "🔴 즉시 매도 / 교체 (Cut Loss)"
            sell_reason = f"[{stock_name}] 주가 하락과 퀀트 총점({total_score}점) 악화가 동반되었습니다."
            action = "전량 매도 후 다른 우량주로 교체 매수를 권장합니다."
            sell_rank_score = 90
    else:
        sell_signal = "🟢 보유 유지 (Hold)"
        sell_reason = f"[{stock_name}] 주간 추세가 안정적으로 유지되고 있습니다."
        action = f"상향 목표가({target_profit}) 도달 시까지 보유 유지."
        sell_rank_score = 20

    return sell_signal, sell_reason, action, target_profit, stop_loss, sell_rank_score

def process_single_stock(ticker, market, name_map, engine, macro):
    stock_name = name_map.get(ticker, ticker.split('.')[0])
    try:
        df = yf.Ticker(ticker).history(period='1y', timeout=3)
    except Exception:
        df = pd.DataFrame()
    
    raw = engine.calculate_raw_scores(df, macro, market, stock_name)
    r_1w_val, r_today, r_1d, r_2d, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)
    
    code = ticker.split('.')[0]
    link = f"https://finance.naver.com/item/main.naver?code={code}" if ticker.endswith(('.KS', '.KQ')) else f"https://finance.yahoo.com/quote/{ticker}"
    
    row = {
        '시장': market,
        '종목명': stock_name,
        '차트링크': f"[{stock_name}]({link})",
        'r_1w_val': r_1w_val,
        '당일 수익률': r_today,
        '1일 전': r_1d,
        '2일 전': r_2d,
        '1주 수익률': r_1w,
        '1달 수익률': r_1m,
        '3개월 수익률': r_3m,
        '1년 수익률': r_1y
    }
    for i, fn in enumerate(FEATURE_NAMES):
        row[fn] = np.round(raw[i], 1)
        
    for p in ["1~3D", "1~2W", "1~3M", "1Y+"]:
        row[f"총점_{p}"] = engine.calculate_v3_score(raw, market, p, r_1w_val, macro)
        row[f"미래수익률_{p}"] = engine.calculate_pure_future_return(raw, market, p, r_1w_val, macro)
    return row

@st.cache_data(ttl=3600)
def run_quant_analysis():
    universe, name_map = UniverseLoader.get_full_universe()
    engine, macro = QuantEngine(), fetch_realtime_macro()
    tasks = [(ticker, m) for m, tickers in universe.items() for ticker in tickers]
    results = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(process_single_stock, t, m, name_map, engine, macro) for t, m in tasks]
        for f in futures:
            try:
                r = f.result()
                if r: results.append(r)
            except Exception: pass
    return pd.DataFrame(results), engine, macro

# ==========================================
# 5. 대시보드 UI (2단계 개편 적용)
# ==========================================
st.set_page_config(page_title="AI 추천 주식 매매 (v4.00)", layout="wide")
if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=30000, key="quant_loop")

st.title("📈 AI 추천 주식 매매 (v4.00)")
st.caption(f"부제 4.00 - 2단계: 다변화 정렬 옵션 & 오버슈팅 방지 매매전략 리포트 적용 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

df, engine, macro_info = run_quant_analysis()

# 실시간 지수 카드
cols = st.columns(6)
idx_list = [("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ"), ("S&P 500", "S&P500"), ("NASDAQ", "NASDAQ"), ("원/달러 환율", "USDKRW"), ("VIX", "VIX")]
for col, (lbl, k) in zip(cols, idx_list):
    d = macro_info.get(k, {'val':0.0, 'change':0.0})
    col.metric(lbl, f"{d['val']:,.2f}", f"{d['change']:+.2f}%")

st.markdown("---")

FIXED_CATEGORIES = [
    '🏆 통합 전체 유니버스 (국내+미국 종합)',
    '코스피200',
    '코스닥100',
    'S&P500',
    '나스닥100'
]

if not df.empty:
    tabs = st.tabs(["⚡ 단기 (1~3일)", "🌊 스윙 (1~2주)", "📊 중기 (1~3개월)", "🏛️ 장기 (1년 이상)"])
    period_codes = ["1~3D", "1~2W", "1~3M", "1Y+"]

    for tab, p_code in zip(tabs, period_codes):
        with tab:
            st.markdown(f"### 🎯 [{p_code}] 투자 호흡별 맞춤형 스크리닝 및 순위 정렬")
            
            for cat in FIXED_CATEGORIES:
                col_head1, col_head2 = st.columns([3, 1])
                with col_head1:
                    st.markdown(f"### 🏆 {cat} Top 10")
                with col_head2:
                    cat_sort_opt = st.selectbox(
                        "정렬 옵션 선택:",
                        options=[
                            "퀀트점수 순", 
                            "미래 기대 수익률 순 (%)", 
                            "🟢 안전 눌림목 TOP 10", 
                            "🔥 단기 수급/모멘텀 TOP 10",
                            "🔴 매도/손절 대응 순"
                        ],
                        index=0,
                        key=f"sort_{cat}_{p_code}"
                    )

                cat_df = df.drop_duplicates(subset=['종목명']).copy() if "통합" in cat else df[df['시장'] == cat].copy()
                
                if not cat_df.empty:
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                    cat_df['예측수익률(%)'] = cat_df[f"미래수익률_{p_code}"]
                    
                    probs, b_sigs, s_sigs, s_ranks = [], [], [], []
                    for _, r in cat_df.iterrows():
                        p_val, b_sig, _ = generate_buy_analysis(r, macro_info)
                        s_sig, _, _, _, _, s_rank = generate_sell_analysis(r)
                        probs.append(p_val)
                        b_sigs.append(b_sig)
                        s_sigs.append(s_sig)
                        s_ranks.append(s_rank)
                    
                    cat_df['상승확률(%)'] = probs
                    cat_df['매도우선순위'] = s_ranks

                    # 2단계 다변화 정렬 필터 적용
                    if "미래 기대 수익률" in cat_sort_opt:
                        cat_df = cat_df.sort_values(by=['예측수익률(%)', '상승확률(%)'], ascending=[False, False]).head(10)
                    elif "안전 눌림목" in cat_sort_opt:
                        temp_df = cat_df[(cat_df['총점'] >= 50) & (cat_df['r_1w_val'] >= -7.0) & (cat_df['r_1w_val'] <= 3.0)]
                        if not temp_df.empty: cat_df = temp_df
                        cat_df = cat_df.sort_values(by=['상승확률(%)', '총점'], ascending=[False, False]).head(10)
                    elif "단기 수급/모멘텀" in cat_sort_opt:
                        cat_df['모멘텀합산'] = cat_df['수급/거래량'] + cat_df['기술적모멘텀']
                        cat_df = cat_df.sort_values(by=['모멘텀합산', '총점'], ascending=[False, False]).head(10)
                    elif "매도/손절" in cat_sort_opt:
                        cat_df = cat_df.sort_values(by=['매도우선순위', 'r_1w_val'], ascending=[False, False]).head(10)
                    else:
                        cat_df = cat_df.sort_values(by=['총점', '상승확률(%)'], ascending=[False, False]).head(10)

                    disp_cols = ['차트링크', '시장', '당일 수익률', '1주 수익률', '총점', '예측수익률(%)'] + FEATURE_NAMES
                    st.write(cat_df[[c for c in disp_cols if c in cat_df.columns]].reset_index(drop=True).to_markdown(), unsafe_allow_html=True)
                    
                    # 2단계 상세 매매 전략 리포트
                    with st.expander(f"🔍 [{cat}] 종목별 실시간 매수/매도 전략 상세 리포트"):
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            prob, buy_signal, buy_opinion = generate_buy_analysis(row, macro_info)
                            s_signal, s_reason, action, target_p, stop_l, _ = generate_sell_analysis(row)
                            
                            st.markdown(f"### {idx}. {row['종목명']} ({row['시장']} | 예측 수익률: `+{row['예측수익률(%)']}%` | 상승 확률: `{prob}%` | 퀀트 총점: `{row['총점']}`점)")
                            st.markdown(f"#### 📈 **[매수 분석]** 상승 기대 확률: `{prob}%` | 시그널: `{buy_signal}`")
                            st.info(f"💡 **매수 의견:** {buy_opinion}")
                            
                            st.markdown(f"#### 📉 **[매도 분석]** 시그널: `{s_signal}`")
                            st.markdown(f"- 🎯 **목표 익절가:** `{target_p}` | 🛑 **손절 기준:** `{stop_l}`")
                            st.warning(f"💡 **진단 이유:** {s_reason}\n\n👉 **대응 전략:** {action}")
                            st.markdown("---")
