"""Non-destructive validation of the saved batch universe.

Batch rows are NOT interchangeable with live-scored recommendations.
"""
from pathlib import Path
import pandas as pd


def inspect_batch(frame, live_tickers=()):
    if frame is None or frame.empty:
        return {'rows': 0, 'unique': 0, 'duplicates': 0, 'overlap': 0, 'missing_ticker': 0, 'missing_price': None, 'columns': [], 'ticker_column': None, 'price_column': None}
    ticker_col = next((c for c in ('티커', 'ticker', 'Ticker', 'symbol', 'Symbol') if c in frame.columns), None)
    price_col = next((c for c in ('종가', 'close', 'Close', 'price', 'Price', '기준종가') if c in frame.columns), None)
    if ticker_col is None:
        return {'rows': len(frame), 'unique': 0, 'duplicates': 0, 'overlap': 0, 'missing_ticker': len(frame), 'missing_price': None, 'columns': list(frame.columns), 'ticker_column': None, 'price_column': price_col}
    symbols = frame[ticker_col].astype('string').str.strip()
    good = symbols.notna() & symbols.ne('')
    clean = symbols[good]
    missing_price = None
    if price_col is not None:
        price = pd.to_numeric(frame[price_col], errors='coerce')
        missing_price = int((price.isna() | (price <= 0)).sum())
    return {'rows': len(frame), 'unique': int(clean.nunique()), 'duplicates': int(clean.duplicated().sum()), 'overlap': len(set(clean) & set(live_tickers)), 'missing_ticker': int((~good).sum()), 'missing_price': missing_price, 'columns': list(frame.columns), 'ticker_column': ticker_col, 'price_column': price_col}


def load_batch(path='quant_stocks.parquet'):
    path = Path(path)
    if not path.is_file():
        return None, '배치 파일이 없습니다.'
    try:
        return pd.read_parquet(path), None
    except Exception as exc:
        return None, f'배치 파일 읽기 실패: {type(exc).__name__}'
