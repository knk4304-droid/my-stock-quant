"""Data-quality helpers shared by dashboard and batch jobs."""
import math
import pandas as pd


def valid_prices(df, minimum=6):
    if df is None or df.empty or 'Close' not in df:
        return False
    prices = pd.to_numeric(df['Close'], errors='coerce').dropna()
    return len(prices) >= minimum and bool((prices > 0).all()) and bool(prices.map(math.isfinite).all())


def return_summary(df):
    """Returns for 1, 5, 21, 63 and 252 completed trading sessions."""
    if not valid_prices(df, 2):
        raise ValueError('Insufficient valid closing prices')
    c = pd.to_numeric(df['Close'], errors='coerce').dropna()
    def ret(days, offset=0):
        end = len(c)-1-offset
        start = end-days
        if start < 0:
            return None
        return (float(c.iloc[end])/float(c.iloc[start])-1)*100
    def fmt(v):
        return 'N/A' if v is None else f'{v:+.2f}%'
    weekly=ret(5)
    return (round(weekly,2) if weekly is not None else 0.0,
            fmt(ret(1)),fmt(ret(1,1)),fmt(ret(1,2)),fmt(weekly),
            fmt(ret(21)),fmt(ret(63)),fmt(ret(252)))


def valid_macro_value(value):
    try:
        return math.isfinite(float(value)) and float(value)>0
    except (TypeError,ValueError):
        return False
