import yfinance as yf
import pandas as pd
import numpy as np

def run_20y_backtest(ticker):
    """과거 주가 흐름 적용 시 시그널 적중률 및 MDD 계산 엔진"""
    try:
        # 최근 20년치 주가 데이터 수집
        data = yf.download(ticker, period="20y", interval="1d", progress=False)
        if data.empty:
            return None
            
        # 이동평균선 기반 기술적 매수/매도 시그널 예시
        close_prices = data['Close']
        ma20 = close_prices.rolling(20).mean()
        ma60 = close_prices.rolling(60).mean()
        signal = np.where(ma20 > ma60, 1, 0)
        
        # 수익률 calculation
        returns = close_prices.pct_change()
        strategy_returns = returns * pd.Series(signal, index=data.index).shift(1)
        
        cum_returns = (1 + strategy_returns.fillna(0)).cumprod()
        peak = cum_returns.cummax()
        mdd = ((cum_returns - peak) / peak).min() * 100
        
        valid_trades = strategy_returns[strategy_returns != 0]
        win_rate = (valid_trades > 0).sum() / len(valid_trades) * 100 if len(valid_trades) > 0 else 0
        
        return {
            "Total_Return": (cum_returns.iloc[-1] - 1) * 100,
            "MDD": mdd,
            "Win_Rate": win_rate,
            "History_DF": cum_returns
        }
    except Exception as e:
        print(f"백테스팅 연산 오류: {e}")
        return None
