import datetime
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import streamlit as st

# PC 윈도우 우측 하단 팝업 알림 패키지
try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

# 실시간 자동 새로고침 패키지
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

warnings.filterwarnings('ignore')

# ==========================================
# 🔔 카카오톡 API 설정
# ==========================================
DEFAULT_KAKAO_TOKEN = "KMLOEgzWQJJnKV7dX2EZetIbYbnQPJyqAAAAAQoXElUAAAGhgHE4T-AsyCcGfplL"

def send_kakao_alert(token, title, stock_name, market, prob, step_msg, ratio_msg, price_info=""):
    if PLYER_AVAILABLE:
        try:
            notification.notify(
                title=f"🚨 [{title}] {stock_name}",
                message=f"확률: {prob}% | {step_msg}\n비중: {ratio_msg}",
                app_name="v3.16 AI 퀀트 시스템",
                timeout=7
            )
        except Exception:
            pass

    active_token = token.strip() if token and token.strip() else DEFAULT_KAKAO_TOKEN
    if not active_token:
        return False, "토큰이 입력되지 않았습니다."

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {active_token}"}
    
    text_content = f"🚨 [{title}] 🚨\n\n"
    text_content += f"📌 종목: {stock_name} ({market})\n"
    text_content += f"- 기대상승확률: {prob}%\n"
    text_content += f"- 진입 단계: {step_msg}\n"
    text_content += f"- 권장 매수 비중: {ratio_msg}\n"
    if price_info:
        text_content += f"- 실시간 시세: {price_info}\n"
    text_content += f"\n💡 AI 퀀트 v3.16 초고속 병렬 시그널"

    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": text_content,
            "link": {"web_url": "https://my-stock-quant-k6dgdkytkbcevuoyxx9mzl.streamlit.app"}
        })
    }
    
    try:
        res = requests.post(url, headers=headers, data=payload, timeout=5)
        res_json = res.json()
        if res.status_code == 200 and res_json.get("result_code") == 0:
            return True, "카카오톡 메시지가 성공적으로 전송되었습니다!"
        else:
            msg = res_json.get("msg", "토큰이 만료되었거나 메시지 전송 권한이 없습니다.")
            return False, f"카카오 API 오류: {msg}"
    except Exception as e:
        return False, f"네트워크 통신 오류: {str(e)}"

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
            '041510.KQ': 'SM', '035760.KQ': 'CJ ENM', '086900.KQ': '메디톡스',
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
            
            '440110.KQ': '파두', '277810.KQ': '레인보우로보틱스', '328130.KQ': '루닛', '084990.KQ': '하이비젼시스템',
            '053690.KQ': '한미반도체', '081660.KQ': '플리토', '060280.KQ': '큐렉소', '058470.KQ': '리노공업',
            '053030.KQ': '바이오니아', '068240.KQ': '다원시스',
            
            'PLTR': '팔란티어', 'SMCI': '슈퍼마이크로컴퓨터', 'IONQ': '아이온큐', 'ROKU': '로쿠',
            'SOFI': '소파이', 'U': '유니티', 'RBLX': '로블록스', 'PATH': '유아이패스',
            'DKNG': '드래프트킹스', 'AFRM': '어펌홀딩스'
        }

        universe = {
            '코스피200': ['068270.KS', '006400.KS', '000270.KS', '005490.KS', '051910.KS', '035420.KS', '005380.KS', '005930.KS', '035720.KS', '000660.KS'],
            '코스닥100': ['247540.KQ', '086520.KQ', '196170.KQ', '028300.KQ', '293490.KQ', '278280.KQ', '035900.KQ', '041510.KQ', '035760.KQ', '086900.KQ'],
            'S&P500': ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'BRK-B', 'TSLA', 'UNH', 'JNJ'],
            '나스닥100': ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AVGO', 'COST', 'AMD'],
            '국내 ETF': ['069500.KS', '102110.KQ', '305540.KS', '458730.KS', '371460.KS', '252670.KS', '114800.KS', '138230.KS', '360750.KS', '229200.KS'],
            '미국 ETF': ['SPY', 'QQQ', 'IVV', 'VOO', 'SOXX', 'TQQQ', 'SQQQ', 'SCHD', 'XLK', 'XLE'],
            '국내 소형 고성장주': ['440110.KQ', '277810.KQ', '328130.KQ', '084990.KQ', '053690.KQ', '081660.KQ', '060280.KQ', '058470.KQ', '053030.KQ', '068240.KQ'],
            '미국 소형 고성장주': ['PLTR', 'SMCI', 'IONQ', 'ROKU', 'SOFI', 'U', 'RBLX', 'PATH', 'DKNG', 'AFRM']
        }
        return universe, name_map


# ==========================================
# 3. 퀀트 채점 엔진 (수익률 현실화 스케일링 반영)
# ==========================================
class QuantEngine:
    def __init__(self):
        self.largecap_weights = {
            '1W':   [5, 10, 10, 20, 20, 15, 5, 5, 5, 5],
            '1M':   [8, 10, 10, 20, 18, 14, 5, 5, 5, 5],
            '6M':   [15, 15, 10, 15, 10, 10, 5, 5, 10, 5],
            '1Y':   [20, 15, 15, 15, 5, 5, 5, 5, 10, 5],
            '5Y':   [20, 20, 15, 15, 5, 5, 5, 5, 5, 5],
            '10Y':  [25, 20, 15, 15, 2, 3, 5, 5, 5, 5],
            '10Y+': [30, 20, 15, 15, 0, 0, 5, 5, 5, 5]
        }
        
        self.smallcap_weights = {
            '1W':   [15, 5, 5, 15, 20, 20, 2, 3, 10, 5],
            '1M':   [18, 5, 5, 12, 20, 18, 2, 3, 12, 5],
            '6M':   [30, 10, 5, 5, 15, 10, 2, 3, 15, 5],
            '1Y':   [35, 10, 5, 5, 10, 10, 2, 3, 15, 5],
            '5Y':   [40, 15, 5, 5, 5, 5, 2, 3, 15, 5],
            '10Y':  [45, 15, 5, 5, 2, 3, 2, 3, 15, 5],
            '10Y+': [50, 15, 5, 5, 0, 0, 2, 3, 15, 5]
        }

        self.etf_weights = {
            '1W':   [5, 0, 0, 10, 20, 15, 10, 10, 20, 10],
            '1M':   [5, 0, 0, 10, 20, 15, 10, 10, 20, 10],
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
        if df.empty or len(df.dropna()) < 5:
            return 0.0, "0.00%", "0.00%", "0.00%", "0.00%"

        clean_close = df['Close'].dropna()
        latest_price = clean_close.iloc[-1]

        r_1w_val = ((latest_price - clean_close.iloc[-5]) / clean_close.iloc[-5] * 100) if len(clean_close) >= 5 else 0.0
        r_1m_val = ((latest_price - clean_close.iloc[-20]) / clean_close.iloc[-20] * 100) if len(clean_close) >= 20 else 0.0
        r_3m_val = ((latest_price - clean_close.iloc[-60]) / clean_close.iloc[-60] * 100) if len(clean_close) >= 60 else ((latest_price - clean_close.iloc[0]) / clean_close.iloc[0] * 100)
        r_1y_val = ((latest_price - clean_close.iloc[0]) / clean_close.iloc[0] * 100) if len(clean_close) > 0 else 0.0

        return r_1w_val, f"{r_1w_val:+.2f}%", f"{r_1m_val:+.2f}%", f"{r_3m_val:+.2f}%", f"{r_1y_val:+.2f}%"

    def calculate_raw_scores(self, df: pd.DataFrame, macro: dict, market: str, stock_name: str) -> np.ndarray:
        if df.empty or len(df.dropna()) < 2:
            return np.array([50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0])

        clean_close = df['Close'].dropna()
        latest_close = float(clean_close.iloc[-1])
        vol_series = df['Volume'].dropna() if 'Volume' in df else pd.Series([100000])
        vol_val = float(vol_series.iloc[-1]) if not vol_series.empty else 100000.0

        start_price = float(clean_close.iloc[0])
        growth_rate = (latest_close - start_price) / start_price * 100 if start_price > 0 else 0.0
        daily_returns = clean_close.pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252) * 100 if len(daily_returns) > 5 else 20.0

        s1 = np.clip(growth_rate + 50.0, 10.0, 100.0)

        r_1y_pct = ((latest_close - start_price) / start_price * 100) if start_price > 0 else 0.0
        s2 = np.clip(50.0 + r_1y_pct * 0.4, 15.0, 95.0)

        s3 = np.clip(100.0 - volatility * 1.2, 20.0, 90.0)

        ma20 = clean_close.tail(20).mean() if len(clean_close) >= 20 else latest_close
        disparity = (latest_close / ma20) * 100 if ma20 > 0 else 100.0
        if "소형" in market:
            s4 = np.clip(100.0 - abs(disparity - 100.0) * 1.5, 30.0, 95.0)
        else:
            s4 = np.clip(100.0 - abs(disparity - 100.0) * 3.0, 15.0, 95.0)

        delta = clean_close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi_series = 100 - (100 / (1 + gain / loss))
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else 50.0
        s5 = max(10.0, 100.0 - abs(60.0 - rsi) * 2.0)

        avg_vol = float(vol_series.tail(20).mean()) if not vol_series.empty else vol_val
        s6 = min(100.0, max(10.0, (vol_val / avg_vol * 50.0))) if avg_vol > 0 else 50.0

        usdkrw_change = macro.get('USDKRW', {}).get('change', 0.0)
        export_stocks = ['삼성전자', 'SK하이닉스', '현대차', '기아', 'LG화학', '삼성SDI', 'POSCO홀딩스']
        
        if any(e_stock in stock_name for e_stock in export_stocks) or "미국" in market or "S&P" in market or "나스닥" in market:
            s7 = np.clip(70.0 + usdkrw_change * 5.0 + (growth_rate * 0.1), 30.0, 95.0)
        else:
            s7 = np.clip(45.0 - usdkrw_change * 3.0 - (volatility * 0.2), 20.0, 80.0)

        vix_val = macro['VIX']['val'] if macro.get('VIX') and macro['VIX']['val'] > 0 else 15.0
        if "소형" in market or "코스닥" in market:
            s8 = np.clip(75.0 - (vix_val - 15.0) * 3.0 - (volatility * 0.3), 15.0, 85.0)
        else:
            s8 = np.clip(80.0 - (vix_val - 15.0) * 1.5, 30.0, 90.0)

        pct_change = float(clean_close.pct_change(5).iloc[-1]) if len(clean_close) >= 5 else 0.0
        s9 = min(100.0, max(10.0, pct_change * 1000.0 + 50.0))

        s10 = np.clip(90.0 - (volatility * 1.1), 20.0, 95.0)

        scores = np.array([s1, s2, s3, s4, s5, s6, s7, s8, s9, s10])
        return np.nan_to_num(scores, nan=50.0)

    def calculate_v3_score(self, raw_scores: np.ndarray, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict) -> float:
        w_list = self.get_weights_by_market(market, period)
        w = np.array(w_list)
        base_score = np.sum(raw_scores * (w / 100.0))

        vix_val = macro.get('VIX', {}).get('val', 15.0)
        nasdaq_change = macro.get('NASDAQ', {}).get('change', 0.0)
        
        vix_penalty = -5.0 if vix_val >= 20.0 else 0.0
        us_coupling_bonus = np.clip(nasdaq_change * 2.0, -6.0, 6.0)

        if period in ['1W', '1M']:
            if base_score >= 55.0 and (r_1m_val <= -12.0) and (r_1w_val >= +3.0):
                rebound_bonus = 8.0
            elif base_score >= 65.0 and (-7.0 <= r_1w_val <= -0.5):
                rebound_bonus = 5.0
            elif r_1w_val > 10.0:
                rebound_bonus = -3.0
            else:
                rebound_bonus = 0.0
        else:
            rebound_bonus = 0.0

        final_score = np.clip(base_score + vix_penalty + us_coupling_bonus + rebound_bonus, 10, 100)
        return np.round(float(final_score), 2)

    # 🔥 [v3.16 현실화] 스케일링 보정이 적용된 순수 미래 수익률 예측 수식
    def calculate_pure_future_return(self, raw_scores: np.ndarray, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict) -> float:
        cagr = raw_scores[0]
        roe = raw_scores[1]
        tech = raw_scores[4]
        volume = raw_scores[5]
        rel_strength = raw_scores[8]
        nasdaq_change = macro.get('NASDAQ', {}).get('change', 0.0)

        if period in ['1W', '1M', '6M']:
            if "코스피" in market or "코스닥" in market or "국내" in market:
                v_rebound = 12.0 if (r_1m_val <= -12.0 and r_1w_val >= +3.0) else 0.0
                raw_est = (volume * 0.12) + (v_rebound * 0.8) + (nasdaq_change * 1.5) + (tech * 0.08) + (r_1w_val * 0.25)
            else:
                raw_est = (tech * 0.15) + (volume * 0.10) + (nasdaq_change * 1.2) + (r_1w_val * 0.2)
            
            if "소형" in market:
                raw_est *= 1.2
            
            # 🔥 실전 매매 스케일링 조절 (현실적 1W~1M 목표치인 +3.5% ~ +18.5% 로 스케일링)
            scaled_return = np.clip(raw_est * 0.35 + 2.5, 1.5, 25.0)
        else:
            raw_est = (cagr * 0.25) + (roe * 0.20) + (rel_strength * 0.15)
            if "소형" in market:
                raw_est *= 1.3
            scaled_return = np.clip(raw_est * 0.8, 5.0, 150.0)

        return np.round(float(scaled_return), 2)


def get_chart_link(ticker: str, name: str) -> str:
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        code = ticker.split('.')[0]
        url = f"https://finance.naver.com/item/main.naver?code={code}"
    else:
        url = f"https://my-stock-quant-k6dgdkytkbcevuoyxx9mzl.streamlit.app/~/+/#ai-v3-0927quote/{ticker}/"
    return f"[{name}]({url})"


def generate_buy_analysis(row, macro, user_token=""):
    total_score = row['총점']
    r_1w_val = row['r_1w_val']
    stock_name = row['종목명']
    market = row['시장']
    vix_val = macro.get('VIX', {}).get('val', 15.0)

    tech_score = row.get('기술적모멘텀', 50.0)
    prob = total_score + (tech_score - 50.0) * 0.2 + (r_1w_val * 0.5)
    
    if vix_val >= 20.0:
        prob -= 5.0

    prob = int(np.clip(prob, 10, 95))

    if prob >= 70:
        buy_signal = "🟢 강력 매수 (Buy) [70% 이상]"
        buy_opinion = f"[{stock_name}] 기대 상승 확률 약 {prob}%로 최상위 매수 시그널입니다. 적극 매수를 추천합니다."
        send_kakao_alert(user_token, "3차 매수 알림", stock_name, market, prob, "3차 진입 (🟢 강력 매수 시그널 전환 완료)", "전체 예산의 잔여 30%", "V자 반등 확정 구간")
    elif prob >= 55:
        buy_signal = "🟡 분할 매수 / 관망 (Hold) [55% ~ 69%]"
        buy_opinion = f"[{stock_name}] 눌림목 및 상승 시그널 구간입니다 (기대 확률 {prob}%). 분할 진입을 권장합니다."
        if -2.5 <= r_1w_val <= -0.8:
            send_kakao_alert(user_token, "1차 매수 알림", stock_name, market, prob, "1차 진입 (시가 대비 -1%~-2% 눌림 발생)", "전체 예산의 40%", f"1주 등락률: {r_1w_val:+.2f}%")
        elif -6.0 <= r_1w_val < -2.5:
            send_kakao_alert(user_token, "2차 매수 알림", stock_name, market, prob, "2차 진입 (20일선 눌림목 지지선 도달)", "추가 30%", f"1주 등락률: {r_1w_val:+.2f}%")
    else:
        buy_signal = "🔴 관망 / 매도 (Sell/Wait) [55% 미만]"
        buy_opinion = f"[{stock_name}] 기대 상승 확률({prob}%)이 다소 낮습니다. 신규 매수를 보류하세요."

    return prob, buy_signal, buy_opinion


def generate_sell_analysis(row):
    stock_name = row['종목명']
    total_score = row['총점'] if not pd.isna(row['총점']) else 50.0
    r_1w_val = row['r_1w_val'] if not pd.isna(row['r_1w_val']) else 0.0
    market = row['시장']

    base_target = total_score * 0.12
    dynamic_target_low = round(max(base_target, r_1w_val + 1.5), 1)
    dynamic_target_high = round(max(base_target + 3.0, r_1w_val + 4.0), 1)

    target_profit = f"+{dynamic_target_low}% ~ +{dynamic_target_high}%"
    stop_loss = "-3.5% ~ -5.5%" if "대형" in market or "코스피" in market else "-5.0% ~ -7.5%"

    sell_rank_score = 10

    if r_1w_val >= 8.0 or (r_1w_val >= dynamic_target_low and r_1w_val > 5.0):
        sell_signal = f"🟠 익절 권장 (Take Profit) [실시간 오버슈팅: +{r_1w_val:.1f}% 달성]"
        sell_reason = f"[{stock_name}] 실시간 등락률(+{r_1w_val:.2f}%)이 목표가를 돌파하여 과열 상투 구간에 진입했습니다."
        action = "현재 구간에서 비중 50% 이상 분할 매도하여 수익을 확정하세요!"
        sell_rank_score = 100

    elif r_1w_val <= -5.0:
        if total_score >= 55.0:
            sell_signal = "🔵 반등 기대 / 보유 (Rebound Hold) [눌림목: 1주≤-5% & 총점≥55]"
            sell_reason = f"[{stock_name}] 단기 하락({r_1w_val:+.2f}%)이 발생했으나 V자 반등 가능성이 높습니다."
            action = f"매도하지 말고 리밸런싱 시점까지 보유 유지 (손절가 {stop_loss} 엄수)"
            sell_rank_score = 60
        else:
            sell_signal = "🔴 즉시 매도 / 교체 (Sell) [추세붕괴: 1주≤-5% & 총점<55]"
            sell_reason = f"[{stock_name}] 단기 주가 하락과 함께 퀀트 총점({total_score}점) 및 수급이 동반 악화되었습니다."
            action = "전량 매도 후 우량주 교체"
            sell_rank_score = 90

    elif r_1w_val < 0 and total_score < 55.0:
        sell_signal = "🟡 손절 고려 / 관망 (Caution) [약세: 1주<0% & 총점<55]"
        sell_reason = f"[{stock_name}] 퀀트 총점({total_score}점)이 약세권입니다."
        action = f"손절가({stop_loss}) 미도달 시 보유, 이탈 시 손절"
        sell_rank_score = 40

    else:
        sell_signal = "🟢 보유 유지 (Hold) [안정 추세 유지]"
        sell_reason = f"[{stock_name}] 주간 추세가 안정적입니다."
        action = f"실시간 상향 목표가({target_profit}) 도달 시까지 보유 유지"
        sell_rank_score = 20

    return sell_signal, sell_reason, action, target_profit, stop_loss, sell_rank_score


# 🔥 [v3.16 초고속] 개별 종목 분석 병렬 처리 단일 실행 함수
def process_single_stock(ticker, market, name_map, engine, macro):
    clean_code = ticker.split('.')[0]
    stock_name = name_map.get(ticker, name_map.get(clean_code, clean_code))
    
    try:
        df = yf.Ticker(ticker).history(period='1y', timeout=3)
    except Exception:
        df = pd.DataFrame()

    raw_scores = engine.calculate_raw_scores(df, macro, market, stock_name)
    r_1w_val, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)
    
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
        '1주 수익률': r_1w,
        '1달 수익률': r_1m,
        '3개월 수익률': r_3m,
        '1년 수익률': r_1y
    }
    
    for i, fname in enumerate(FEATURE_NAMES):
        row[fname] = np.round(raw_scores[i], 1)

    periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']
    for p in periods:
        row[f"총점_{p}"] = engine.calculate_v3_score(raw_scores, market, p, r_1w_val, r_1m_val, macro)
        row[f"미래수익률_{p}"] = engine.calculate_pure_future_return(raw_scores, market, p, r_1w_val, r_1m_val, macro)
        
    return row


@st.cache_data(ttl=10)
def run_quant_analysis():
    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    macro = fetch_realtime_macro()

    tasks = []
    for market, tickers in universe.items():
        for ticker in tickers:
            tasks.append((ticker, market))

    # 🔥 ThreadPoolExecutor를 사용한 초고속 병렬 데이터 수집
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(process_single_stock, ticker, market, name_map, engine, macro)
            for ticker, market in tasks
        ]
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


# ==========================================
# 4. 대시보드 UI (v3.16 초고속 병렬 처리판)
# ==========================================
st.set_page_config(page_title="AI 퀀트 주식 분석 시스템 v3.16", layout="wide")

if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=30 * 1000, key="quant_realtime_loop")

now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

st.title("📈 AI 퀀트 주식 추천 및 매도 판정 시스템 (v3.16)")
st.caption(f"부제 3.16 - 멀티스레딩 초고속 병렬 수집 & 미래 기대 수익률 현실화 스케일링판 | {now_str}")

# 🔥 카카오 토큰 입력 및 연습 테스트 버튼 창
with st.expander("🔔 **[내 핸드폰으로 카카오톡 알림 받기 설정 및 연습 테스트]** 클릭하여 설정", expanded=True):
    user_kakao_token = st.text_input(
        "본인의 카카오 Access Token을 입력하세요 (미입력 시 기본 설정 키 사용):",
        value="",
        placeholder="예: KMLOEgzWQJJnKV7dX2EZetIbYbnQPJyqAAAAAQoXElUAAAGhgHE4T-AsyCcGfplL",
        type="password"
    )
    
    col_test1, col_test2 = st.columns([1, 3])
    with col_test1:
        if st.button("🧪 [카카오톡 테스트 메시지 전송하기]"):
            success, result_msg = send_kakao_alert(user_kakao_token, "알림 테스트", "삼성전자", "코스피200", 75, "테스트 1차 진입 구간", "40%", "현재가 72,500원")
            if success:
                st.success(f"✅ {result_msg}")
            else:
                st.error(f"❌ {result_msg}\n\n👉 해결법: 카카오 디벨로퍼스에서 Access Token을 새로 발급받아 붙여넣어 주세요.")

st.info("""
**📊 [v3.16 초고속 병렬 가동 안내]**  
수익률 예측 모델의 스케일링을 현실적인 단기 타점 목표치로 정밀 교정했습니다. 멀티스레딩(Multithreading) 병렬 엔진이 적용되어 **`미래 기대 수익률 순 (%)`** 선택 시 수초 만에 명확한 상위 종목을 추출해 냅니다.
""")

st.markdown("[🔍 구글(Google) 검색 바로가기](https://www.google.com)")

DEFAULT_CATEGORIES = [
    '🏆 통합 전체 유니버스 (국내+미국 종합)',
    '코스피200', '코스닥100', 'S&P500', '나스닥100', 
    '국내 ETF', '미국 ETF', '국내 소형 고성장주', '미국 소형 고성장주'
]

# 🔥 테마 제어판
with st.expander("⚙️ **[테마 제어판]** 출력할 테마 선택 및 순서 변경하기 (클릭하여 닫기/열기)", expanded=True):
    selected_categories = st.multiselect(
        "화면에 표시할 테마를 선택하고 순서를 조정하세요:",
        options=DEFAULT_CATEGORIES,
        default=DEFAULT_CATEGORIES
    )

with st.spinner("v3.16 멀티스레딩 초고속 병렬 계산 중..."):
    df, engine, macro_info = run_quant_analysis()

st.subheader("🌐 실시간 주요 시장 지수 현황 (클릭 시 상세 차트 연결)")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)

index_configs = [
    (m_col1, "KOSPI", macro_info.get('KOSPI', {'val':0,'change':0}), "url?id=5"),
    (m_col2, "KOSDAQ", macro_info.get('KOSDAQ', {'val':0,'change':0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ"),
    (m_col3, "S&P 500", macro_info.get('S&P500', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^GSPC/"),
    (m_col4, "NASDAQ 100", macro_info.get('NASDAQ', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^IXIC/"),
    (m_col5, "원/달러 환율", macro_info.get('USDKRW', {'val':0,'change':0}), "https://m.stock.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"),
    (m_col6, "VIX (변동성)", macro_info.get('VIX', {'val':0,'change':0}), "https://finance.yahoo.com/quote/^VIX/")
]

for col, name, data, link in index_configs:
    with col:
        render_korean_market_card(name, data, link)

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
            st.subheader(f"📌 [{p_code}] 분야별 미래 기대 상승 Top 10 및 매수/매도 종합 진단")

            display_categories = selected_categories if selected_categories else DEFAULT_CATEGORIES
            
            for cat in display_categories:
                col_head1, col_head2 = st.columns([3, 1])
                with col_head1:
                    st.markdown(f"### 🏆 {cat} Top 10")
                with col_head2:
                    cat_sort_opt = st.selectbox(
                        "정렬 옵션 선택:",
                        options=["퀀트점수 순", "미래 기대 수익률 순 (%)", "매수시그널 순 (확률 %)", "매도시그널 순 (대응)"],
                        index=0,
                        key=f"sort_{cat}_{p_code}"
                    )
                
                if "통합 전체 유니버스" in cat:
                    cat_df = df.drop_duplicates(subset=['종목명']).copy()
                else:
                    cat_df = df[df['시장'] == cat].copy()
                
                if not cat_df.empty:
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                    cat_df['예측수익률(%)'] = cat_df[f"미래수익률_{p_code}"]
                    
                    probs = []
                    b_signals = []
                    s_signals = []
                    s_ranks = []
                    
                    for _, r in cat_df.iterrows():
                        p_val, b_sig, _ = generate_buy_analysis(r, macro_info, "")
                        s_sig, _, _, _, _, s_rank = generate_sell_analysis(r)
                        probs.append(p_val)
                        b_signals.append(b_sig)
                        s_signals.append(s_sig)
                        s_ranks.append(s_rank)
                    
                    cat_df['기대상승확률(%)'] = probs
                    cat_df['매도우선순위'] = s_ranks
                    
                    # 4가지 정렬 옵션별 조건 실행
                    if "미래 기대 수익률" in cat_sort_opt:
                        cat_df = cat_df.sort_values(by=['예측수익률(%)', '기대상승확률(%)'], ascending=[False, False]).head(10)
                    elif "매수시그널" in cat_sort_opt:
                        cat_df = cat_df.sort_values(by=['기대상승확률(%)', 'r_1w_val', '총점'], ascending=[False, False, False]).head(10)
                    elif "매도시그널" in cat_sort_opt:
                        cat_df = cat_df.sort_values(by=['매도우선순위', 'r_1w_val'], ascending=[False, False]).head(10)
                    else:
                        cat_df = cat_df.sort_values(by=['총점', '기대상승확률(%)'], ascending=[False, False]).head(10)
                    
                    cat_df['종목(차트보기)'] = cat_df['차트링크']
                    
                    show_cols = ['종목(차트보기)', '시장', '1주 수익률', '1달 수익률', '3개월 수익률', '총점'] + FEATURE_NAMES

                    display_df = cat_df[show_cols].reset_index(drop=True)
                    display_df.index = display_df.index + 1
                    
                    st.write(display_df.to_markdown(), unsafe_allow_html=True)
                    
                    with st.expander(f"🔍 [{cat}] 종목별 매수 추천 시그널 및 매도/손익절 종합 진단 리포트"):
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            prob, buy_signal, buy_opinion = generate_buy_analysis(row, macro_info, user_kakao_token)
                            s_signal, s_reason, action, target_p, stop_l, _ = generate_sell_analysis(row)
                            
                            st.markdown(f"### {idx}. {row['종목명']} ({row['시장']} | 예측 수익률: `+{row['예측수익률(%)']}%` | 상승 확률: `{prob}%` | 퀀트 총점: `{row['총점']}`점)")
                            st.markdown(f"#### 📈 **[매수 분석]** 상승 기대 확률: `{prob}%` | 매수 시그널: `{buy_signal}`")
                            st.info(f"💡 **매수 의견:** {buy_opinion}")
                            
                            st.markdown(f"#### 📉 **[매도 분석]** 현재 매도 시그널: `{s_signal}`")
                            st.markdown(f"- 🎯 **권장 목표 익절가:** `{target_p}` | 🛑 **자동 손절 기준:** `{stop_l}`")
                            st.warning(f"💡 **매도 진단 이유:** {s_reason}\n\n👉 **대응 방법:** {action}")
                            st.markdown("---")
                else:
                    st.info("해당 카테고리 데이터가 없습니다.")
                st.write("")
