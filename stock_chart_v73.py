"""Validated daily close chart data; never interpret as real-time quotes."""
import pandas as pd


def prepare_close_chart(history):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or 'Close' not in history:
        return pd.DataFrame(), '유효한 일별 종가가 없습니다.'
    close = pd.to_numeric(history['Close'], errors='coerce')
    dates = pd.to_datetime(history.index, errors='coerce', utc=True)
    result = pd.DataFrame({'거래일': dates.date, '종가': close.to_numpy()})
    result = result.dropna(subset=['거래일', '종가'])
    result = result[result['종가'] > 0].drop_duplicates('거래일', keep='last').sort_values('거래일')
    if len(result) < 2:
        return pd.DataFrame(), '차트에 필요한 유효한 거래일이 2일 미만입니다.'
    return result.reset_index(drop=True), None


def change_percent(prices):
    if prices is None or len(prices) < 2:
        return None
    start, end = float(prices['종가'].iloc[0]), float(prices['종가'].iloc[-1])
    return (end / start - 1) * 100 if start > 0 else None
