"""Explicitly hypothetical price scenarios, never forecast or trading advice."""
import math

def build_trade_plan(close, stop_pct=4.0, currency='KRW'):
    p, s = float(close), float(stop_pct)
    if not (math.isfinite(p) and p > 0 and math.isfinite(s) and 0 < s <= 10):
        raise ValueError('유효한 기준가와 손실 가정 비율이 필요합니다.')
    round_price = lambda x: round(x, 2)
    return {'통화':currency, '기준 종가':round_price(p), '1차 진입 가정(-2%)':round_price(p*.98),
            '2차 진입 가정(-4%)':round_price(p*.96), '1차 목표 가정(+4%)':round_price(p*1.04),
            '2차 목표 가정(+8%)':round_price(p*1.08), '손실 제한 가정':round_price(p*(1-s/100)),
            '가정 손익비(2차 목표 기준)':round(8/s,2)}

def get_reference_quote(ticker):
    try:
        import yfinance as yf
        symbols=[ticker]
        if ticker.endswith(('.KS','.KQ')):
            symbols.append(ticker[:-3]+('.KQ' if ticker.endswith('.KS') else '.KS'))
        for symbol in symbols:
            try:
                history=yf.Ticker(symbol).history(period='10d', interval='1d', timeout=8, auto_adjust=False)
                if history is None or history.empty or 'Close' not in history: continue
                closes=history['Close'].dropna()
                if closes.empty: continue
                price=float(closes.iloc[-1])
                if not math.isfinite(price) or price<=0: continue
                date=closes.index[-1].strftime('%Y-%m-%d')
                return {'close':price,'date':date,'currency':'KRW' if symbol.endswith(('.KS','.KQ')) else 'USD',
                        'source':'Yahoo Finance (일별 종가)', 'ticker':symbol}
            except Exception:
                continue
        return {'error':'유효한 최근 종가를 확인하지 못했습니다. 데이터 공급원·티커를 확인하세요.'}
    except Exception as exc:
        return {'error':f'시세 조회 준비 실패: {type(exc).__name__}'}
