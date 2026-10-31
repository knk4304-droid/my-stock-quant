# quant.py - v4.00 정밀 퀀트 연산 엔진
import warnings
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import yfinance as yf

warnings.filterwarnings('ignore')

POS_KW = ['수주', '흑자', '최대실적', '상승', '호실적', '신기술', '특허', '강세', '인수', '호재']
NEG_KW = ['적자', '감소', '유상증자', '하락', '소송', '악재', '부진', '횡령', '이탈', '경고', '리스크']

def fetch_stock_news_sentiment(clean_code):
    try:
        url = f"https://finance.naver.com/item/news_news.naver?code={clean_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code != 200:
            return 0.0, 0, 0

        soup = BeautifulSoup(res.text, 'html.parser')
        titles = [a.text.strip() for a in soup.select('.title a')[:5]]
        if not titles:
            return 0.0, 0, 0

        pos_cnt = sum(1 for t in titles for k in POS_KW if k in t)
        neg_cnt = sum(1 for t in titles for k in NEG_KW if k in t)

        total = pos_cnt + neg_cnt
        if total == 0:
            return 0.0, pos_cnt, neg_cnt

        score = round(((pos_cnt - neg_cnt) / total) * 100, 1)
        return score, pos_cnt, neg_cnt
    except Exception:
        return 0.0, 0, 0

class QuantEngine:
    def __init__(self):
        pass

    def get_weights_by_market(self, market: str, period: str) -> list:
        if period in ['1W', '1M']:
            if market == '국내 ETF':
                return [0.05, 0.05, 0.05, 0.10, 0.20, 0.15, 0.05, 0.05, 0.20, 0.10]
            elif market in ['코스피200', '코스닥100']:
                return [0.10, 0.10, 0.08, 0.10, 0.20, 0.15, 0.05, 0.05, 0.12, 0.05]
            else:
                return [0.12, 0.12, 0.08, 0.10, 0.18, 0.12, 0.05, 0.05, 0.13, 0.05]
        else:
            return [0.20, 0.18, 0.12, 0.15, 0.08, 0.05, 0.05, 0.05, 0.07, 0.05]

    def calculate_returns(self, df: pd.DataFrame):
        try:
            if df.empty or len(df.dropna()) < 2:
                return 0.0, "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%"
            
            close = df['Close'].dropna()
            curr = close.iloc[-1]
            
            r_today = (curr / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0.0
            r_1d = (close.iloc[-2] / close.iloc[-3] - 1) * 100 if len(close) >= 3 else 0.0
            r_2d = (close.iloc[-3] / close.iloc[-4] - 1) * 100 if len(close) >= 4 else 0.0
            r_1w = (curr / close.iloc[-5] - 1) * 100 if len(close) >= 5 else 0.0
            r_1m = (curr / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0.0
            r_3m = (curr / close.iloc[-60] - 1) * 100 if len(close) >= 60 else 0.0
            r_1y = (curr / close.iloc[0] - 1) * 100
            
            r_1w_val = round(r_1w, 2)
            fmt = lambda v: f"{'+' if v > 0 else ''}{v:.2f}%"
            
            return r_1w_val, fmt(r_today), fmt(r_1d), fmt(r_2d), fmt(r_1w), fmt(r_1m), fmt(r_3m), fmt(r_1y)
        except Exception:
            return 0.0, "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%"

    def calculate_raw_scores(self, df: pd.DataFrame, macro: dict, market: str, stock_name: str, news_score: float = 0.0) -> list:
        if df.empty or len(df.dropna()) < 5:
            return [50.0] * 10

        close = df['Close'].dropna()
        volume = df['Volume'].dropna() if 'Volume' in df else pd.Series([1]*len(close))

        r_1m = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0.0
        r_1y = (close.iloc[-1] / close.iloc[0] - 1) * 100
        
        cagr_score = np.clip(50.0 + r_1y * 0.5, 10.0, 100.0)
        momentum_score = np.clip(50.0 + r_1m * 1.5, 10.0, 100.0)

        vol_ratio = (volume.iloc[-1] / volume.iloc[-5:].mean()) if len(volume) >= 5 and volume.iloc[-5:].mean() > 0 else 1.0
        supply_score = np.clip(50.0 + (vol_ratio - 1.0) * 20.0 + (news_score * 0.2), 10.0, 100.0)

        vix_val = macro.get('VIX', {}).get('val', 15.0)
        macro_score = np.clip(80.0 - (vix_val - 15.0) * 2.0, 20.0, 100.0)

        raw = [
            cagr_score, 65.0, 70.0, 60.0, momentum_score, supply_score,
            70.0, 65.0, np.clip(50.0 + r_1m, 10.0, 100.0), macro_score
        ]
        return [round(float(x), 1) for x in raw]

    def calculate_v3_score(self, raw_scores: list, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict, news_score: float = 0.0) -> float:
        weights = self.get_weights_by_market(market, period)
        base_score = float(np.sum(np.array(raw_scores) * np.array(weights)))
        news_bonus = (news_score / 100.0) * 3.0
        return round(float(np.clip(base_score + news_bonus, 10.0, 100.0)), 2)

    def calculate_pure_future_return(self, raw_scores: list, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict, news_score: float = 0.0) -> float:
        score = self.calculate_v3_score(raw_scores, market, period, r_1w_val, r_1m_val, macro, news_score)
        base_return = (score - 50.0) * 0.25
        ret = base_return * 0.6 + (news_score * 0.02) if period == '1W' else (base_return * 1.2 if period == '1M' else base_return * 2.5)
        return round(float(ret), 2)


def generate_buy_analysis(row, macro_info):
    prob = int(min(95, max(60, row.get('총점_1W', row.get('총점', 50.0)) * 1.1 + row.get('news_score', 0.0) * 0.05)))
    r_1w = row.get('r_1w_val', 0.0)
    stock_name = row.get('종목명', '선택종목')

    if prob >= 70 and r_1w < 8.0:
        buy_signal = "🟢 강력 매수 (Buy) [70% 이상]"
        opinion = f"[{stock_name}] 기대 상승 확률 약 {prob}%로 최상위 매수 시그널입니다. 적극 매수를 추천합니다."
    elif prob >= 70 and r_1w >= 8.0:
        buy_signal = f"🟡 매수 보류 / 눌림목 대기 (Wait for Dip) [단기 오버슈팅: {r_1w:+.1f}% 달성]"
        opinion = f"[{stock_name}] 상승 모멘텀(기대 확률 {prob}%)은 우수하나, 최근 1주 등락률({r_1w:+.1f}%)이 급등하여 단기 과열 상태입니다. 신규 진입을 보류하고 눌림목 조정을 기다리세요."
    else:
        buy_signal = f"🟡 분할 매수 / 관망 (Hold) [{prob}%]"
        opinion = f"[{stock_name}] 상승 시그널 구간입니다 (기대 확률 {prob}%). 분할 진입을 권장합니다."

    return prob, buy_signal, opinion


def generate_sell_analysis(row):
    r_1w = row.get('r_1w_val', 0.0)
    score = row.get('총점_1W', row.get('총점', 50.0))
    neg_c = int(row.get('news_neg', 0))
    stock_name = row.get('종목명', '선택종목')

    target_price = f"+{round(score * 0.15, 1)}% ~ +{round(score * 0.18, 1)}%"
    stop_loss = "-3.5% ~ -5.5%" if "코스피" in str(row.get('시장', '')) else "-5.0% ~ -7.5%"

    if r_1w <= -5.0 and score < 55.0 and neg_c > 0:
        s_signal = "🔴 손절/교체 (Sell & Switch) [악재 발생 & 총점 약세]"
        reason = f"[{stock_name}] 최근 주가 하락({r_1w:.1f}%)과 악재 뉴스 발생({neg_c}건), 퀀트 점수 약세({score}점)로 즉시 손절/교체를 권장합니다."
        action = "손절 후 우량주 교체"
        rank = 1
    elif r_1w >= 8.0:
        s_signal = f"🟠 익절 권장 (Take Profit) [실시간 오버슈팅: {r_1w:+.1f}% 달성]"
        reason = f"[{stock_name}] 실시간 등락률({r_1w:+.1f}%)이 목표가를 돌파하여 과열 상투 구간에 진입했습니다."
        action = "보유 비중 50% 분할 익절"
        rank = 2
    elif r_1w <= -5.0 and score >= 55.0:
        s_signal = "🔵 반등 기대 / 보유 (Rebound Hold) [눌림목: 1주≤-5% & 총점≥55]"
        reason = f"[{stock_name}] 단기 하락({r_1w:.1f}%)이 발생했으나 펀더멘털 점수({score}점)가 살아있어 V자 반등 가능성이 높습니다."
        action = "보유 유지 및 추매 대기"
        rank = 3
    else:
        s_signal = "🟢 보유 유지 (Hold) [안정 추세 유지]"
        reason = f"[{stock_name}] 주간 추세가 안정적입니다."
        action = "보유 유지"
        rank = 4

    return s_signal, reason, action, target_price, stop_loss, rank
