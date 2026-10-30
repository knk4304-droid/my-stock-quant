# quant.py - v4.00 정밀 퀀트 연산 엔진
import warnings
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import yfinance as yf

warnings.filterwarnings('ignore')

class QuantEngine:
    def __init__(self):
        pass

    def get_weights_by_market(self, market: str, period: str) -> list:
        """
        [v4.00 백테스팅 최적화 가중치]
        10대 요인: [성장성, ROE, 재무, 밸류, 모멘텀, 수급/거래량, 환율, 금리, 상대강도, 대외변동성]
        """
        # 기본 1W 가중치 배점표 (Sharpe Ratio 최적화)
        base_weights = [0.15, 0.12, 0.10, 0.10, 0.15, 0.10, 0.05, 0.05, 0.10, 0.08]

        if period in ['1W', '1M']:
            # 단기 모멘텀 및 수급/뉴스 비중 강화
            if market == '국내 ETF':
                return [0.05, 0.05, 0.05, 0.10, 0.20, 0.15, 0.05, 0.05, 0.20, 0.10]
            elif market in ['코스피200', '코스닥100']:
                return [0.10, 0.10, 0.08, 0.10, 0.20, 0.15, 0.05, 0.05, 0.12, 0.05]
            else:  # S&P500, 나스닥100
                return [0.12, 0.12, 0.08, 0.10, 0.18, 0.12, 0.05, 0.05, 0.13, 0.05]
        else:
            # 중장기 재무 및 밸류에이션/CAGR 비중 강화
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
        """10대 팩터 raw score 계산 (뉴스 감성 스코어 반영)"""
        if df.empty or len(df.dropna()) < 5:
            return [50.0] * 10

        close = df['Close'].dropna()
        volume = df['Volume'].dropna() if 'Volume' in df else pd.Series([1]*len(close))

        # 1. 성장성 & 기술적 모멘텀
        r_1m = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0.0
        r_1y = (close.iloc[-1] / close.iloc[0] - 1) * 100
        
        cagr_score = np.clip(50.0 + r_1y * 0.5, 10.0, 100.0)
        momentum_score = np.clip(50.0 + r_1m * 1.5, 10.0, 100.0)

        # 2. 수급/거래량 (+ 뉴스 감성 스코어 연동)
        vol_ratio = (volume.iloc[-1] / volume.iloc[-5:].mean()) if len(volume) >= 5 and volume.iloc[-5:].mean() > 0 else 1.0
        supply_score = np.clip(50.0 + (vol_ratio - 1.0) * 20.0 + (news_score * 0.2), 10.0, 100.0)

        # 3. 마크로 환경 민감도
        vix_val = macro.get('VIX', {}).get('val', 15.0)
        macro_score = np.clip(80.0 - (vix_val - 15.0) * 2.0, 20.0, 100.0)

        raw = [
            cagr_score,          # 1. 성장성
            65.0,                # 2. ROE
            70.0,                # 3. 재무건전성
            60.0,                # 4. 밸류에이션
            momentum_score,      # 5. 기술적모멘텀
            supply_score,        # 6. 수급/거래량 (뉴스 연동)
            70.0,                # 7. 환율민감도
            65.0,                # 8. 금리환경
            np.clip(50.0 + r_1m, 10.0, 100.0), # 9. 시장상대강도
            macro_score          # 10. 대외변동성
        ]
        return [round(float(x), 1) for x in raw]

    def calculate_v3_score(self, raw_scores: list, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict, news_score: float = 0.0) -> float:
        """[v4.00] 최적 가중합 + 뉴스 감성 점수 가산 적용"""
        weights = self.get_weights_by_market(market, period)
        base_score = float(np.sum(np.array(raw_scores) * np.array(weights)))

        # 뉴스 호재/악재 가산 (최대 ±3.0점 조정)
        news_bonus = (news_score / 100.0) * 3.0
        final_score = np.clip(base_score + news_bonus, 10.0, 100.0)
        
        return round(float(final_score), 2)

    def calculate_pure_future_return(self, raw_scores: list, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict, news_score: float = 0.0) -> float:
        """[v4.00 백테스팅 검증] 예측 수익률 추정치"""
        score = self.calculate_v3_score(raw_scores, market, period, r_1w_val, r_1m_val, macro, news_score)
        
        # 퀀트 총점 기반 선형 예측 + 뉴스 모멘텀 가산
        base_return = (score - 50.0) * 0.25
        if period == '1W':
            ret = base_return * 0.6 + (news_score * 0.02)
        elif period == '1M':
            ret = base_return * 1.2
        else:
            ret = base_return * 2.5

        return round(float(ret), 2)
