"""Conservative market-data parsing and multi-source USD/KRW retrieval."""
import math
import requests


def positive_number(value):
    try:
        v = float(str(value).replace(',', ''))
        return v if math.isfinite(v) and v > 0 else None
    except (ValueError, TypeError):
        return None


def rate_from_history(history):
    if history is None or history.empty or 'Close' not in history:
        return None
    values = [positive_number(x) for x in history['Close'].tolist()]
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {'val': round(values[-1], 2), 'change': round((values[-1] / values[-2] - 1) * 100, 2) if len(values) > 1 else None,
            'source': 'Yahoo Finance', 'asof': str(history.index[-1])}


def fetch_usdkrw(yf_module, requests_module=requests, timeout=4):
    """No fabricated FX quote; return None when both sources fail."""
    for ticker in ('KRW=X', 'USDKRW=X'):
        try:
            result = rate_from_history(yf_module.Ticker(ticker).history(period='5d', timeout=timeout))
            if result and 500 <= result['val'] <= 3000:
                result['source'] = 'Yahoo Finance ' + ticker
                return result
        except (ValueError, TypeError, KeyError, requests.RequestException, RuntimeError):
            pass
    try:
        r = requests_module.get('https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        value = positive_number(data.get('closePrice'))
        if value is not None and 500 <= value <= 3000:
            return {'val': value, 'change': safe_signed(data.get('fluctuationsRatio')),
                    'source': 'Naver Finance', 'asof': data.get('localTradedAt') or data.get('date')}
    except (ValueError, TypeError, KeyError, requests.RequestException, RuntimeError):
        pass
    return {'val': None, 'change': None, 'source': 'unavailable', 'asof': None}


def safe_signed(value):
    try:
        v = float(str(value).replace(',', ''))
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None
