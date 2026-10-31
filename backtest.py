# backtest.py - 과거 20년 백테스팅 검증 엔진
import yfinance as yf
import pandas as pd
import numpy as np

def run_20y_backtest(ticker):
    try:
        data = yf.download(ticker, period="20y", interval="1d", progress=False)
        if data.empty:
            return None
            
        close_prices = data['Close']
        if isinstance(close_prices, pd.DataFrame):
            close_prices = close_prices.iloc[:, 0]

        ma20 = close_prices.rolling(20).mean()
        ma60 = close_prices.rolling(60).mean()
        signal = np.where(ma20 > ma60, 1, 0)
        
        returns = close_prices.pct_change()
        strategy_returns = returns * pd.Series(signal, index=data.index).shift(1)
        
        cum_returns = (1 + strategy_returns.fillna(0)).cumprod()
        peak = cum_returns.cummax()
        mdd = ((cum_returns - peak) / peak).min() * 100
        
        valid_trades = strategy_returns[strategy_returns != 0]
        win_rate = (valid_trades > 0).sum() / len(valid_trades) * 100 if len(valid_trades) > 0 else 0
        
        return {
            "Total_Return": round(float((cum_returns.iloc[-1] - 1) * 100), 2),
            "MDD": round(float(mdd), 2),
            "Win_Rate": round(float(win_rate), 2),
            "History_DF": cum_returns
        }
    except Exception as e:
        print(f"백테스팅 연산 오류: {e}")
        return None
