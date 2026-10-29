import numpy as np
import pandas as pd

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
            return 0.0, "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%", "0.00%"

        clean_close = df['Close'].dropna()
        latest_price = clean_close.iloc[-1]

        r_today_val = ((clean_close.iloc[-1] - clean_close.iloc[-2]) / clean_close.iloc[-2] * 100) if len(clean_close) >= 2 else 0.0
        r_1d_val = ((clean_close.iloc[-2] - clean_close.iloc[-3]) / clean_close.iloc[-3] * 100) if len(clean_close) >= 3 else 0.0
        r_2d_val = ((clean_close.iloc[-3] - clean_close.iloc[-4]) / clean_close.iloc[-4] * 100) if len(clean_close) >= 4 else 0.0

        r_1w_val = ((latest_price - clean_close.iloc[-5]) / clean_close.iloc[-5] * 100) if len(clean_close) >= 5 else 0.0
        r_1m_val = ((latest_price - clean_close.iloc[-20]) / clean_close.iloc[-20] * 100) if len(clean_close) >= 20 else 0.0
        r_3m_val = ((latest_price - clean_close.iloc[-60]) / clean_close.iloc[-60] * 100) if len(clean_close) >= 60 else ((latest_price - clean_close.iloc[0]) / clean_close.iloc[0] * 100)
        r_1y_val = ((latest_price - clean_close.iloc[0]) / clean_close.iloc[0] * 100) if len(clean_close) > 0 else 0.0

        return (
            r_1w_val,
            f"{r_today_val:+.2f}%", f"{r_1d_val:+.2f}%", f"{r_2d_val:+.2f}%",
            f"{r_1w_val:+.2f}%", f"{r_1m_val:+.2f}%", f"{r_3m_val:+.2f}%", f"{r_1y_val:+.2f}%"
        )

    def calculate_raw_scores(self, df: pd.DataFrame, macro: dict, market: str, stock_name: str) -> np.ndarray:
        if df.empty or len(df.dropna()) < 2:
            return np.array([50.0] * 10)

        clean_close = df['Close'].dropna()
        latest_close = float(clean_close.iloc[-1])
        vol_series = df['Volume'].dropna() if 'Volume' in df else pd.Series([100000])
        vol_val = float(vol_series.iloc[-1]) if not vol_series.empty else 100000.0

        start_price = float(clean_close.iloc[0])
        growth_rate = (latest_close - start_price) / start_price * 100 if start_price > 0 else 0.0
        daily_returns = clean_close.pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252) * 100 if len(daily_returns) > 5 else 20.0

        s1 = np.clip(growth_rate + 50.0, 10.0, 100.0)
        s2 = np.clip(50.0 + growth_rate * 0.4, 15.0, 95.0)
        s3 = np.clip(100.0 - volatility * 1.2, 20.0, 90.0)

        ma20 = clean_close.tail(20).mean() if len(clean_close) >= 20 else latest_close
        disparity = (latest_close / ma20) * 100 if ma20 > 0 else 100.0
        s4 = np.clip(100.0 - abs(disparity - 100.0) * (1.5 if "소형" in market else 3.0), 15.0, 95.0)

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
        s8 = np.clip(75.0 - (vix_val - 15.0) * 3.0 - (volatility * 0.3), 15.0, 85.0)

        pct_change = float(clean_close.pct_change(5).iloc[-1]) if len(clean_close) >= 5 else 0.0
        s9 = min(100.0, max(10.0, pct_change * 1000.0 + 50.0))
        s10 = np.clip(90.0 - (volatility * 1.1), 20.0, 95.0)

        scores = np.array([s1, s2, s3, s4, s5, s6, s7, s8, s9, s10])
        return np.nan_to_num(scores, nan=50.0)

    def calculate_v3_score(self, raw_scores: np.ndarray, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict) -> float:
        w = np.array(self.get_weights_by_market(market, period))
        base_score = np.sum(raw_scores * (w / 100.0))

        vix_val = macro.get('VIX', {}).get('val', 15.0)
        nasdaq_change = macro.get('NASDAQ', {}).get('change', 0.0)
        vix_penalty = -5.0 if vix_val >= 20.0 else 0.0
        us_coupling_bonus = np.clip(nasdaq_change * 2.0, -6.0, 6.0)

        rebound_bonus = 0.0
        if period in ['1W', '1M']:
            if base_score >= 55.0 and (r_1m_val <= -12.0) and (r_1w_val >= +3.0):
                rebound_bonus = 8.0
            elif base_score >= 65.0 and (-7.0 <= r_1w_val <= -0.5):
                rebound_bonus = 5.0
            elif r_1w_val > 10.0:
                rebound_bonus = -3.0

        final_score = np.clip(base_score + vix_penalty + us_coupling_bonus + rebound_bonus, 10, 100)
        return np.round(float(final_score), 2)

    def calculate_pure_future_return(self, raw_scores: np.ndarray, market: str, period: str, r_1w_val: float, r_1m_val: float, macro: dict) -> float:
        cagr, roe, tech, volume, rel_strength = raw_scores[0], raw_scores[1], raw_scores[4], raw_scores[5], raw_scores[8]
        nasdaq_change = macro.get('NASDAQ', {}).get('change', 0.0)

        if period in ['1W', '1M', '6M']:
            v_rebound = 12.0 if (r_1m_val <= -12.0 and r_1w_val >= +3.0) else 0.0
            raw_est = (volume * 0.12) + (v_rebound * 0.8) + (nasdaq_change * 1.5) + (tech * 0.08) + (r_1w_val * 0.25)
            if "소형" in market:
                raw_est *= 1.2
            scaled_return = np.clip(raw_est * 0.35 + 2.5, 1.5, 25.0)
        else:
            raw_est = (cagr * 0.25) + (roe * 0.20) + (rel_strength * 0.15)
            if "소형" in market:
                raw_est *= 1.3
            scaled_return = np.clip(raw_est * 0.8, 5.0, 150.0)

        return np.round(float(scaled_return), 2)

def generate_buy_analysis(row, macro):
    total_score = row.get('총점', 50.0)
    r_1w_val = row.get('r_1w_val', 0.0)
    stock_name = row.get('종목명', '')
    vix_val = macro.get('VIX', {}).get('val', 15.0)

    tech_score = row.get('기술적모멘텀', 50.0)
    prob = total_score + (tech_score - 50.0) * 0.2 + (r_1w_val * 0.5)
    if vix_val >= 20.0:
        prob -= 5.0

    prob = int(np.clip(prob, 10, 95))

    if r_1w_val >= 8.0:
        buy_signal = f"🟡 매수 보류 / 눌림목 대기 (Wait for Dip) [단기 오버슈팅: {r_1w_val:+.1f}% 달성]"
        buy_opinion = f"[{stock_name}] 상승 모멘텀(기대 확률 {prob}%)은 우수하나, 주가가 최근 1주 동안 과도하게 급등({r_1w_val:+.2f}%)하여 과열 상태입니다. 신규 매수를 보류하고 눌림목 조정을 기다리세요."
    elif prob >= 70:
        buy_signal = "🟢 강력 매수 (Buy) [70% 이상]"
        buy_opinion = f"[{stock_name}] 기대 상승 확률 약 {prob}%로 최상위 매수 시그널입니다. 적극 매수를 추천합니다."
    elif prob >= 55:
        buy_signal = "🟡 분할 매수 / 관망 (Hold) [55% ~ 69%]"
        buy_opinion = f"[{stock_name}] 눌림목 및 상승 시그널 구간입니다 (기대 확률 {prob}%). 분할 진입을 권장합니다."
    else:
        buy_signal = "🔴 관망 / 매도 (Sell/Wait) [55% 미만]"
        buy_opinion = f"[{stock_name}] 기대 상승 확률({prob}%)이 다소 낮습니다. 신규 매수를 보류하세요."

    return prob, buy_signal, buy_opinion

def generate_sell_analysis(row):
    stock_name = row.get('종목명', '')
    total_score = row.get('총점', 50.0) if not pd.isna(row.get('총점', 50.0)) else 50.0
    r_1w_val = row.get('r_1w_val', 0.0) if not pd.isna(row.get('r_1w_val', 0.0)) else 0.0
    market = row.get('시장', '')

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
