import datetime, json, time, warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests, streamlit as st, yfinance as yf
from data_quality import valid_prices, return_summary, valid_macro_value
from stock_insights import classify_product, risk_notice, read_batch_status
from market_data import fetch_usdkrw
from risk_review import scenario_risk_reward, coverage_message
from universe_membership import category_tickers, etf_weights
from ranking_options import SORT_OPTIONS, rank_candidates
from batch_universe_quality import inspect_batch, load_batch
from individual_report import normalize_symbol, report_rows, overall_assessment, price_scenarios

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
# 1. 실시간 주요 지수 수집 (코스피/코스닥 보완)
# ==========================================
def fetch_realtime_macro():
    macro = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    kr_indices = [('KOSPI', 'KOSPI', '^KS11'), ('KOSDAQ', 'KOSDAQ', '^KQ11')]
    for key, code, sym in kr_indices:
        success = False
        try:
            url = f"https://m.stock.naver.com/api/index/{code}/basic"
            res = requests.get(url, headers=headers, timeout=3).json()
            macro[key] = {
                'val': float(res['closePrice'].replace(',', '')),
                'change': float(res['fluctuationsRatio'])
            }
            if macro[key]['val'] > 0:
                success = True
        except Exception:
            pass

        if not success:
            try:
                h = yf.Ticker(sym).history(period='5d', timeout=3)
                if not h.empty and len(h) >= 2:
                    curr = float(h['Close'].iloc[-1])
                    prev = float(h['Close'].iloc[-2])
                    macro[key] = {'val': curr, 'change': (curr - prev) / prev * 100.0}
                else:
                    macro[key] = {'val': None, 'change': None}
            except Exception:
                macro[key] = {'val': None, 'change': None}

    macro['USDKRW'] = fetch_usdkrw(yf, requests)

    for key, sym in [('S&P500', '^GSPC'), ('NASDAQ', '^IXIC'), ('VIX', '^VIX')]:
        try:
            h = yf.Ticker(sym).history(period='5d', timeout=3)
            if not h.empty and len(h) >= 2:
                curr = float(h['Close'].iloc[-1])
                prev = float(h['Close'].iloc[-2])
                macro[key] = {'val': curr, 'change': (curr - prev) / prev * 100.0}
            else:
                macro[key] = {'val': None, 'change': None}
        except Exception:
            macro[key] = {'val': None, 'change': None}
            
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
        elif "ETF" in market: return etf_weights(self.etf_weights)[period]
        return self.largecap_weights[period]

    def calculate_returns(self, df):
        return return_summary(df)

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
        
        vix = macro.get('VIX', {}).get('val') or 15.0
        s5 = np.clip(75.0 - (vix - 15.0) * 3.0 - volatility * 0.3, 15.0, 85.0) if "소형" in market else np.clip(80.0 - (vix - 15.0) * 1.5, 30.0, 90.0)
        s6 = np.clip(gr + 50.0, 10.0, 100.0)
        s7 = np.clip(50.0 + gr * 0.4, 15.0, 95.0)
        ma20 = float(c.tail(20).mean()) if len(c) >= 20 else lc
        s8 = np.clip(100.0 - abs((lc / ma20) * 100.0 - 100.0) * 2.0, 15.0, 95.0) if ma20 > 0 else 50.0
        s9 = np.clip(100.0 - volatility * 1.2, 20.0, 90.0)
        s10 = np.clip(70.0 + (macro.get('USDKRW', {}).get('change') or 0.0) * 5.0, 30.0, 95.0)
        
        scores = np.array([s1, s2, s3, s4, s5, s6, s7, s8, s9, s10])
        return np.nan_to_num(scores, nan=50.0)

    def calculate_v3_score(self, raw, market, period, r_1w, macro):
        w = np.array(self.get_weights(market, period))
        base = np.sum(raw * (w / 100.0))
        vix_p = -5.0 if (macro.get('VIX', {}).get('val') or 15.0) >= 20.0 else 0.0
        return round(float(np.clip(base + vix_p, 10.0, 100.0)), 2)

    def calculate_pure_future_return(self, raw, market, period, r_1w, macro):
        if period in ['1~3D', '1~2W']:
            est = (raw[0] * 0.12) + (raw[1] * 0.08) + (r_1w * 0.25)
            return round(float(np.clip(est * 0.35 + 2.5, 1.5, 25.0)), 2)
        est = (raw[5] * 0.25) + (raw[6] * 0.20) + (raw[2] * 0.15)
        return round(float(np.clip(est * 0.8, 5.0, 150.0)), 2)

# ==========================================
# 4. 매수/매도 진단 및 처리 함수
# ==========================================
def generate_buy_analysis(row, macro):
    total_score = row['총점']
    r_1w_val = row['r_1w_val']
    stock_name = row['종목명']
    tech_score = row.get('기술적모멘텀', 50.0)
    
    prob = int(np.clip(total_score + (tech_score - 50.0) * 0.2 + (r_1w_val * 0.3), 10, 95))
    if (macro.get('VIX', {}).get('val') or 15.0) >= 20.0:
        prob = max(0, prob - 5)

    if r_1w_val >= 8.0:
        buy_signal = "🟠 매수 보류 (과열 오버슈팅)"
        buy_opinion = f"[{stock_name}] 최근 1주 등락률(+{r_1w_val:.1f}%) 급등으로 오버슈팅 구간입니다. 눌림목 조정을 기다리세요."
    elif prob >= 70:
        buy_signal = "🟢 상승 신호 강함 (참고용)"
        buy_opinion = f"[{stock_name}] 상승 신호 점수 {prob}/100로 최상위 매수 시그널입니다. 매수 전 위험과 실제 재무정보를 확인하세요."
    elif prob >= 55:
        buy_signal = "🟡 상승 신호 보통 (참고용)"
        buy_opinion = f"[{stock_name}] 점수 기반 신호는 {prob}/100이며 실제 상승 확률이 아닙니다."
    else:
        buy_signal = "🔴 관망 / 매도 (Wait)"
        buy_opinion = f"[{stock_name}] 상승 신호 점수({prob}/100)이 낮습니다. 신규 매수를 보류하세요."

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
            sell_signal = "🔴 위험 신호 (매도 검토)"
            sell_reason = f"[{stock_name}] 주가 하락과 퀀트 총점({total_score}점) 악화가 동반되었습니다."
            action = "투자 목적과 실제 위험을 확인한 후 보유 여부를 검토하세요."
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
    
    if df.empty or 'Close' not in df or len(df['Close'].dropna()) < 6:
        return None  # 가격이 없는 종목은 중립 점수로 위장하지 않음
    if not valid_prices(df, 6):
        return None
    raw = engine.calculate_raw_scores(df, macro, market, stock_name)
    r_1w_val, r_today, r_1d, r_2d, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)
    
    code = ticker.split('.')[0]
    link = f"https://finance.naver.com/item/main.naver?code={code}" if ticker.endswith(('.KS', '.KQ')) else f"https://finance.yahoo.com/quote/{ticker}"
    
    row = {
        '시장': market,
        '티커': ticker,
        '종목명': stock_name,
        '차트링크': link,
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
    # A ticker can belong to several indices. Keep one fetch, but preserve
    # category membership independently when filtering the display.
    unique_tasks = {ticker: (ticker, market) for market, tickers in reversed(list(universe.items())) for ticker in tickers}
    for ticker in universe.get("국내 ETF", []):
        unique_tasks[ticker] = (ticker, "국내 ETF")
    tasks = list(unique_tasks.values())
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
# 5. 대시보드 UI
# ==========================================
st.set_page_config(page_title="AI 추천 주식 매매 (v5.9)", layout="wide")
if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=30000, key="quant_loop")

st.title("📈 AI 추천 주식 매매 (v5.9)")
st.caption(f"v5.9 통합: 배치 종목 품질 진단·화면 분석 범위 비교·기존 추천 기능 유지 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

df, engine, macro_info = run_quant_analysis()
st.info("안내: 예측수익률은 검증된 미래 수익률이 아닌 규칙 기반 추정치이며, 상승신호점수는 실제 통계적 확률이 아닌 점수 기반 신호 지표입니다. 성장성·ROE·재무건전성 등 일부 화면 항목은 실제 기업 공시자료가 아닌 가격 기반 대용 지표 또는 기본 점수입니다. ETF에 기업 재무점수를 그대로 적용한 값은 투자 판단 근거로 사용하지 마세요.")
if df.empty:
    st.error("유효한 종목 가격 데이터를 수집하지 못했습니다. 데이터 공급원과 네트워크 상태를 확인하세요.")
missing_indices = [k for k in ('KOSPI', 'KOSDAQ', 'S&P500', 'NASDAQ', 'USDKRW', 'VIX')
                   if not valid_macro_value(macro_info.get(k, {}).get('val'))]
if missing_indices:
    st.warning("시세 수집 실패: " + ", ".join(missing_indices) + " (0은 실제 지수가 아닙니다.)")

# 실시간 지수 카드
cols = st.columns(6)
idx_list = [("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ"), ("S&P 500", "S&P500"), ("NASDAQ", "NASDAQ"), ("원/달러 환율", "USDKRW"), ("VIX", "VIX")]
for col, (lbl, k) in zip(cols, idx_list):
    d = macro_info.get(k, {'val':None, 'change':None})
    if not valid_macro_value(d.get('val')):
        col.metric(lbl, "데이터 없음", None)
    else:
        change = d.get("change")
        col.metric(lbl, f"{d['val']:,.2f}", f"{change:+.2f}%" if change is not None else None)

# 배치 데이터와 화면 실시간 조회는 별도 경로임을 명시합니다.
status = read_batch_status()
if status['state'] == 'ok':
    st.caption('📦 ' + status['message'] + ' (배치 저장 시각, 화면 실시간 시세와 별도)')
elif status['state'] == 'stale':
    st.warning('배치 데이터 갱신 지연: ' + status['message'])
else:
    st.caption('📦 ' + status['message'])

with st.expander('🧪 v5.9 배치 종목 품질 및 화면 분석 범위 진단'):
    batch_frame, batch_error = load_batch()
    if batch_error:
        st.warning(batch_error)
    else:
        live_symbols = df['티커'].dropna().astype(str).tolist() if '티커' in df.columns else []
        check = inspect_batch(batch_frame, live_symbols)
        a, b, c, d = st.columns(4)
        a.metric('배치 행 수', f"{check['rows']:,}")
        b.metric('배치 고유 티커', f"{check['unique']:,}")
        c.metric('화면 분석 종목', f"{len(set(live_symbols)):,}")
        d.metric('양쪽 공통 티커', f"{check['overlap']:,}")
        st.caption('배치 데이터와 화면 추천은 서로 다른 분석 엔진을 사용합니다. 공통 티커는 동일 점수 또는 동일 시세를 의미하지 않습니다.')
        st.caption(f"중복 티커 행 {check['duplicates']:,}개 · 티커 누락 {check['missing_ticker']:,}개 · 비정상/누락 가격 {check['missing_price'] if check['missing_price'] is not None else '가격 열 없음'}")
        if not check['ticker_column']:
            st.warning('티커 열을 찾지 못했습니다. 배치 데이터 스키마를 확인하세요.')
        if check['duplicates'] or check['missing_ticker'] or (check['missing_price'] or 0):
            st.warning('배치 품질 경고가 있습니다. 이 데이터를 화면 추천 점수로 자동 변환하지 않습니다.')
        with st.expander('배치 데이터 열 구성 확인'):
            st.write(check['columns'])

# Individual report: existing universe lookup or an explicitly supplied ticker.
with st.expander('📑 개별 종목 종합분석 리포트 (검색·매수·매도 전략)', expanded=False):
    st.caption('기존 분석 종목은 이름 또는 티커로 검색할 수 있습니다. 목록 밖 종목은 정확한 거래소 티커를 입력하세요. 국내 코스닥은 123456.KQ처럼 입력합니다.')
    lookup = st.text_input('종목명 또는 티커', key='v59_report_query').strip()
    if lookup:
        choices = df[df['종목명'].astype(str).str.contains(lookup, case=False, regex=False, na=False) |
                     df['티커'].astype(str).str.contains(lookup, case=False, regex=False, na=False)] if not df.empty else pd.DataFrame()
        if not choices.empty:
            selected = st.selectbox('분석 종목 선택', choices.index.tolist(),
                                    format_func=lambda idx: f"{df.loc[idx, '종목명']} ({df.loc[idx, '티커']})", key='v59_report_choice')
            selected_row = df.loc[selected].to_dict()
        else:
            selected_row = None
            ticker = normalize_symbol(lookup)
            if ticker is None:
                st.warning('검색 결과가 없습니다. 외부 종목은 정확한 티커를 입력하세요 (예: AAPL, 005930.KS, 086520.KQ).')
            elif st.button('해당 티커 가격 조회 후 분석', key='v59_fetch_ticker'):
                with st.spinner('종목 가격 데이터 확인 중...'):
                    try:
                        market = '국내 종목' if ticker.endswith(('.KS', '.KQ')) else '미국/기타 종목'
                        selected_row = process_single_stock(ticker, market, {ticker: ticker}, engine, macro_info)
                        if selected_row is not None:
                            st.session_state['v59_report_extra'] = (ticker, selected_row)
                    except Exception as exc:
                        st.warning('시세 조회가 실패했습니다. 티커·거래소·데이터 공급원 상태를 확인하세요.')
            cached = st.session_state.get('v59_report_extra')
            if selected_row is None and cached and cached[0] == ticker:
                selected_row = cached[1]
            if selected_row is None and ticker is not None:
                st.info('해당 티커의 유효한 가격 데이터를 확보한 뒤 리포트를 표시합니다. 가격이 없으면 임의의 점수를 생성하지 않습니다.')
        if selected_row is not None:
            kind = classify_product(selected_row.get('티커'), selected_row.get('종목명'))
            st.subheader(f"{selected_row.get('종목명')} · 종합 투자 분석")
            assessment, explanation = overall_assessment(selected_row)
            st.markdown(f'**종합 판단: {assessment}** — {explanation}')
            st.caption(f"티커: {selected_row.get('티커')} | 시장: {selected_row.get('시장')} | 유형: {kind}")
            st.warning('이 리포트는 과거 가격 기반 규칙 점수이며 투자 권유나 미래 수익률 예측이 아닙니다. 실시간 호가·기업 공시·실적·뉴스 검증은 포함되지 않습니다.')
            st.dataframe(pd.DataFrame(report_rows(selected_row)), use_container_width=True, hide_index=True)
            st.markdown('**종합의견:** 기간별 점수가 일치하면 방향성이 비교적 일관적이며, 상충하면 매매보다 관찰과 위험 관리가 우선입니다.')
            st.markdown('**매수 전략:** 거래량·추세·지지 구간을 확인하고 분할 진입 여부를 판단하세요. **매도 전략:** 진입 전에 손실한도와 목표 시나리오를 설정하고, 추세 이탈 시 재평가하세요.')
            with st.expander('🎯 내 기준가로 목표·손실 시나리오 계산 (예측값 아님)'):
                st.caption('직접 입력한 기준가와 비율을 이용하는 산술 계산입니다. 실제 시세·추천 목표가가 아닙니다.')
                c1, c2, c3 = st.columns(3)
                with c1:
                    reference = st.number_input('기준가 (해당 종목 거래통화)', min_value=0.0, value=0.0, step=100.0, key='v59_reference')
                with c2:
                    target = st.number_input('가정 목표 수익률 (%)', min_value=0.1, max_value=100.0, value=8.0, step=0.5, key='v59_target')
                with c3:
                    stop = st.number_input('가정 허용 손실률 (%)', min_value=0.1, max_value=100.0, value=4.0, step=0.5, key='v59_stop')
                if reference > 0:
                    scenario = price_scenarios(reference, target, stop)
                    st.dataframe(pd.DataFrame([scenario]), hide_index=True, use_container_width=True)
                else:
                    st.info('기준가를 입력하면 목표·손실 가격을 계산합니다.')
            st.caption('재무·뉴스·공시의 실시간 검증은 포함되지 않습니다. 점수는 상승 확률이 아니며 목표·손실 가격은 사용자 가정에 불과합니다.')
            st.caption(risk_notice(kind))
            if selected_row.get('차트링크'):
                st.link_button('가격 차트 확인', selected_row['차트링크'])

with st.expander('🔎 종목 빠른 검색 및 상품 위험도 (현재 화면 분석 종목 기준)'):
    query = st.text_input('종목명 또는 티커 검색', key='v44_search').strip()
    if query:
        matched = df[df['종목명'].astype(str).str.contains(query, case=False, regex=False, na=False) |
                     df['티커'].astype(str).str.contains(query, case=False, regex=False, na=False)] if '티커' in df.columns else df[df['종목명'].astype(str).str.contains(query, case=False, regex=False, na=False)]
        if matched.empty:
            st.info('현재 분석 대상에서 검색 결과가 없습니다. 전체 시장 검색 기능은 아직 지원하지 않습니다.')
        else:
            for _, item in matched.head(15).iterrows():
                kind = classify_product(item.get('티커', ''), item.get('종목명', ''))
                st.markdown(f"**{item['종목명']}** · {item['시장']} · {kind}")
                st.caption(risk_notice(kind))
                st.caption('단기 점수: ' + str(item.get('총점_1~3D', 'N/A')) + ' / 스윙 점수: ' + str(item.get('총점_1~2W', 'N/A')))

# 추천 스냅샷은 사용자가 CSV로 저장해야 하며 자동으로 성과가 추적되지는 않습니다.
from recommendation_audit import create_snapshot, coverage_report
st.caption('ℹ️ 화면 추천은 제한된 표본입니다. 코스피200/S&P500 등은 전체 구성종목을 보장하지 않는 표본 그룹명이며, 배치 저장 종목과 다릅니다.')
if not df.empty:
    st.caption('📊 화면 분석 대상: ' + str(len(df['티커'].dropna().unique())) + '개 고유 티커 · ' + coverage_report(df))
    if status.get('state') in ('ok', 'stale'):
        st.info(f"배치 저장 {status['saved']}종목과 화면 분석 {df['티커'].nunique()}종목은 별개입니다. 배치 종목 전체가 화면 추천에 포함된 것은 아닙니다.")
    snapshot = create_snapshot(df)
    st.download_button('📥 추천 결과 기록용 CSV 다운로드', snapshot.to_csv(index=False).encode('utf-8-sig'),
                       file_name='recommendation_snapshot.csv', mime='text/csv', key='snapshot_download')
    st.caption('추천 시점의 점수 기록용입니다. 미래 수익률 검증에는 이후 날짜의 실제 가격과 거래비용을 추가로 비교해야 합니다.')
with st.expander('📈 추천 성과 검증 (추천 CSV + 후속 일별 종가 CSV)'):
    st.caption('추천 당시 CSV와 이후 날짜의 가격 CSV(ticker,date,close)를 직접 업로드하면 실제 수익률을 계산합니다. 단순 보유 수익률 비교이며 완전한 백테스트는 아닙니다.')
    recommendation_file = st.file_uploader('추천 스냅샷 CSV', type='csv', key='v47_recommendations')
    prices_file = st.file_uploader('후속 종가 CSV', type='csv', key='v47_prices')
    st.caption('CSV 없이 자동 조회하려면 추천 스냅샷 CSV만 올린 뒤 아래 버튼을 누르세요. 조회는 최대 30개 티커·최근 2년으로 제한됩니다.')
    auto_prices = None
    import hashlib
    current_snapshot_hash = hashlib.sha256(recommendation_file.getvalue()).hexdigest() if recommendation_file is not None else None
    if st.session_state.get('v48_snapshot_hash') != current_snapshot_hash:
        st.session_state.pop('v48_auto_prices', None)
        st.session_state.pop('v48_fetch_status', None)
        st.session_state['v48_snapshot_hash'] = current_snapshot_hash
    if recommendation_file is not None and st.button('📡 후속 가격 자동 조회', key='v48_fetch_prices'):
        from forward_prices import fetch_forward_prices
        try:
            recommendation_file.seek(0)
            with st.spinner('실제 후속 종가 조회 중...'):
                auto_prices, fetch_status = fetch_forward_prices(pd.read_csv(recommendation_file), max_tickers=30)
            st.session_state['v48_auto_prices'] = auto_prices
            st.session_state['v48_fetch_status'] = fetch_status
        except (ValueError, ImportError, pd.errors.ParserError) as exc:
            st.error('자동 가격 조회 실패: ' + str(exc))
    if 'v48_fetch_status' in st.session_state:
        st.caption('자동 조회 결과: ' + st.session_state['v48_fetch_status'])
    if prices_file is None and 'v48_auto_prices' in st.session_state:
        auto_prices = st.session_state['v48_auto_prices']

    fee = st.number_input('편도 거래비용 (bp, 1bp=0.01%)', min_value=0, max_value=1000, value=10, step=5)
    if recommendation_file is not None and (prices_file is not None or auto_prices is not None):
        from performance_review import evaluate
        try:
            history_result = evaluate(pd.read_csv(recommendation_file), pd.read_csv(prices_file) if prices_file is not None else auto_prices, fee)
            if history_result.empty:
                st.info('후속 가격 데이터가 충분하지 않아 평가 가능한 추천이 없습니다.')
            else:
                st.dataframe(history_result, use_container_width=True)
                from forward_prices import summarize_returns
                summary = summarize_returns(history_result)
                if not summary.empty:
                    st.caption('표본별 사후 보유수익률 요약 (거래비용 반영, 미래 성과 보장 아님)')
                    st.dataframe(summary, use_container_width=True)
                st.download_button('📥 성과 검증 CSV 다운로드', history_result.to_csv(index=False).encode('utf-8-sig'),
                                   file_name='recommendation_performance.csv', mime='text/csv')
        except (ValueError, KeyError, pd.errors.ParserError) as exc:
            st.error('파일 형식을 확인하세요: ' + str(exc))

# The archive is generated by the scheduled batch engine, NOT by the live
# Streamlit scoring engine. It is descriptive and may have missing dates.
with st.expander('📚 v5.9 자동 배치 추천 기록 · 관측 성과 및 품질 진단'):
    from pathlib import Path
    from audit_history import evaluate_observed_history
    from model_quality import summarize_archive, observed_return_stats, archive_issues
    archive = Path('recommendation_history.csv')
    if not archive.exists():
        st.info('아직 자동 기록이 없습니다. GitHub 배치 실행 및 파일 반영 이후 표시됩니다.')
    else:
        try:
            recorded = pd.read_csv(archive, dtype={'티커': 'string'}, encoding='utf-8-sig')
            st.caption(f'배치 엔진 기록 {len(recorded):,}건 · 실시간 화면 추천 점수와 별도 · 실제 거래 기록 아님')
            quality = summarize_archive(recorded)
            st.caption(f"기록 품질: {quality['dates']}개 기록일 · {quality['tickers']}개 종목 · 중복 {quality['duplicate_keys']}건 · 잘못된 가격 {quality['invalid_prices']}건")
            if quality['duplicate_keys'] or quality['invalid_prices'] or quality['future_dated'] or quality['invalid_dates'] or quality['price_after_record']:
                st.warning('추천 이력에 품질 문제가 있어 성과 해석에 주의가 필요합니다.')
            st.caption(f"날짜 형식 오류 {quality['invalid_dates']}건 · 가격기준일이 기록일보다 미래인 행 {quality['price_after_record']}건 · 기록일 이후 데이터 혼입 여부는 별도 확인 필요")
            issues = archive_issues(recorded)
            if not issues.empty:
                st.dataframe(issues.head(30), use_container_width=True)
            st.dataframe(recorded.tail(30), use_container_width=True)
            results = evaluate_observed_history(recorded)
            if results.empty:
                st.info('아직 평가에 필요한 이후 거래일 관측값이 충분하지 않습니다.')
            else:
                st.caption('후속 관측 가격 간 수익률이며 실제 거래일·독립 거래·모델 적중률을 의미하지 않습니다. 거래비용·배당 미반영, 누락 거래일 가능. 양의 수익률 비율도 검증된 예측 적중률이 아닙니다.')
                stats = observed_return_stats(results)
                st.dataframe(stats, use_container_width=True)
                st.download_button('📥 배치 성과 CSV', results.to_csv(index=False).encode('utf-8-sig'),
                                   file_name='batch_observed_performance.csv', mime='text/csv')
        except (ValueError, KeyError, OSError, pd.errors.ParserError) as exc:
            st.warning('자동 기록을 읽을 수 없습니다: ' + str(exc))

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
                    st.markdown(f"### 🏆 {cat} 상위 최대 10개")
                with col_head2:
                    cat_sort_opt = st.selectbox(
                        "정렬 옵션 선택:",
                        options=list(SORT_OPTIONS),
                        index=0,
                        key=f"sort_{cat}_{p_code}"
                    )

                # Membership is not exclusive: AAPL may appear in both S&P500 and NASDAQ.
                category_universe, _ = UniverseLoader.get_full_universe()
                cat_df = (df.drop_duplicates(subset=['티커']).copy() if '통합' in cat
                          else df[df['티커'].isin(category_tickers(category_universe, cat))].copy())
                
                if cat_df.empty:
                    st.info(coverage_message(0))
                else:
                    st.caption(coverage_message(len(cat_df)))
                    if "통합" not in cat:
                        st.caption(f"설정 후보 {len(category_tickers(category_universe, cat))}개 중 실제 가격 분석 {len(cat_df)}개 (지수 전체 구성종목 아님)")
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                    cat_df['모형추정치(%)'] = cat_df[f"미래수익률_{p_code}"]
                    
                    probs, b_sigs, s_sigs, s_ranks = [], [], [], []
                    for _, r in cat_df.iterrows():
                        p_val, b_sig, _ = generate_buy_analysis(r, macro_info)
                        s_sig, _, _, _, _, s_rank = generate_sell_analysis(r)
                        probs.append(p_val)
                        b_sigs.append(b_sig)
                        s_sigs.append(s_sig)
                        s_ranks.append(s_rank)
                    
                    cat_df['상승신호점수'] = probs
                    cat_df['매도우선순위'] = s_ranks

                    # Consistent, transparent ranking for every market and horizon.
                    cat_df = rank_candidates(cat_df, cat_sort_opt, limit=10)
                    if cat_sort_opt == SORT_OPTIONS[1]:
                        st.caption('매수 적합순: 과열·급락 여부와 신호 점수를 함께 고려합니다. 조건 미충족 종목은 후순위이며 매수 권유가 아닙니다.')
                    elif cat_sort_opt == SORT_OPTIONS[2]:
                        st.caption('안정성 우선순: 기존 점수와 최근 가격 변화에 근거한 대용 순위입니다. 실제 변동성·최대낙폭·유동성 검증을 대신하지 않습니다.')
                    else:
                        st.caption('종합 추천순: 투자기간별 퀀트 총점 기준이며 검증된 미래 수익률 순위가 아닙니다.')

                    cat_df['상품유형'] = [classify_product(r.get('티커', ''), r.get('종목명', '')) for _, r in cat_df.iterrows()]
                    # Compact decision-support view. All original factors remain available below.
                    core_cols = ['종목명', '차트링크', '시장', '상품유형', '당일 수익률', '1주 수익률', '총점', '상승신호점수', '모형추정치(%)']
                    st.dataframe(cat_df[[c for c in core_cols if c in cat_df.columns]].reset_index(drop=True),
                                 use_container_width=True, hide_index=True,
                                 column_config={'차트링크': st.column_config.LinkColumn('차트 보기', display_text='차트 열기')})
                    with st.expander('📊 세부 평가 지표 전체 보기'):
                        detail_cols = core_cols + FEATURE_NAMES
                        st.dataframe(cat_df[[c for c in detail_cols if c in cat_df.columns]].reset_index(drop=True),
                                     use_container_width=True, hide_index=True,
                                     column_config={'차트링크': st.column_config.LinkColumn('차트 보기', display_text='차트 열기')})
                    if cat_df['상품유형'].str.contains('ETF', na=False).any():
                        st.caption('ETF 포함: 성장성·ROE·재무건전성 등은 기업 공시 기반 실제 재무지표가 아닐 수 있으며 주식과 직접 비교하면 안 됩니다.')
                    
                    # 상세 매매 전략 리포트
                    with st.expander(f"🔍 [{cat}] 종목별 실시간 매수/매도 전략 상세 리포트"):
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            prob, buy_signal, buy_opinion = generate_buy_analysis(row, macro_info)
                            s_signal, s_reason, action, target_p, stop_l, _ = generate_sell_analysis(row)
                            
                            st.caption(risk_notice(classify_product(row.get('티커', ''), row.get('종목명', ''))))
                            st.markdown(f"### {idx}. {row['종목명']} ({row['시장']} | 모형 추정치: `+{row['모형추정치(%)']}%` | 상승 신호 점수: `{prob}/100` | 퀀트 총점: `{row['총점']}`점)")
                            st.markdown(f"#### 📈 **[매수 분석]** 상승 신호 점수: `{prob}/100` | 시그널: `{buy_signal}`")
                            st.info(f"💡 **매수 의견:** {buy_opinion}")
                            
                            st.markdown(f"#### 📉 **[매도 분석]** 시그널: `{s_signal}`")
                            st.markdown(f"- 🎯 **가정한 목표수익률 범위:** `{target_p}` | 🛑 **가정한 손실 제한 범위:** `{stop_l}`")
                            rr = scenario_risk_reward(target_p, stop_l)
                            if rr is not None:
                                st.caption(f"보수적 시나리오 손익비 {rr:.2f}:1 (낮은 목표수익률 ÷ 큰 손실폭). 수수료·슬리피지 미반영. 검증된 기대수익이나 매매 추천이 아닙니다.")
                            st.warning(f"💡 **진단 이유:** {s_reason}\n\n👉 **대응 전략:** {action}")
                            st.markdown("---")
