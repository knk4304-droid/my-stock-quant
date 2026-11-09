"""Observed forward close-to-close returns for past recommendation snapshots.

The reference is the recommendation's historical close, not an executable fill.
Missing Yahoo observations stay missing; no future prices are inferred.
"""
from pathlib import Path
from datetime import datetime, timezone
import os
import pandas as pd

DATA = Path(__file__).resolve().parent / 'market_scan_data'
HORIZONS = (1, 5, 20)


def update_forward_returns(max_tickers=None):
    path = DATA / 'recommendation_history.csv'
    if not path.exists():
        return 'No recommendation history yet'
    df = pd.read_csv(path, dtype={'ticker': str})
    if df.empty:
        return 'No recommendations yet'
    for h in HORIZONS:
        for field in (f'close_{h}d', f'return_{h}d_pct', f'date_{h}d'):
            if field not in df.columns:
                df[field] = pd.NA
    df['entry_date'] = pd.to_datetime(df['entry_date'], errors='coerce')
    df['entry_close'] = pd.to_numeric(df['entry_close'], errors='coerce')
    now = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    due = df[df['entry_date'].notna() & df['entry_close'].gt(0)].copy()
    due = due[due['entry_date'] < now]
    due = due[due[[f'return_{h}d_pct' for h in HORIZONS]].isna().any(axis=1)]
    if due.empty:
        return 'No due observations'
    import yfinance as yf
    cap = max(1, int(max_tickers or os.getenv('VALIDATION_MAX_TICKERS', '40')))
    updated = 0
    queried = 0
    # Oldest recommendations first; limit calls to prevent workflow overload.
    for ticker, rows in due.sort_values('entry_date').groupby('ticker', sort=False):
        if queried >= cap:
            break
        queried += 1
        first = rows['entry_date'].min()
        try:
            bars = yf.Ticker(ticker).history(start=(first - pd.Timedelta(days=3)).date().isoformat(),
                end=(now + pd.Timedelta(days=1)).date().isoformat(), auto_adjust=True, timeout=12)
            if bars is None or bars.empty or 'Close' not in bars:
                continue
            close = pd.to_numeric(bars['Close'], errors='coerce').dropna()
            close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
            close = close[~close.index.duplicated(keep='last')].sort_index()
            for idx, r in rows.iterrows():
                # First next trading session is horizon 1. Never substitute a later day.
                future = close[close.index > r['entry_date']]
                for h in HORIZONS:
                    if pd.notna(df.at[idx, f'return_{h}d_pct']) or len(future) < h:
                        continue
                    observation_date = future.index[h - 1]
                    # Only closed historical sessions, not today's possibly incomplete bar.
                    if observation_date >= now:
                        continue
                    px = float(future.iloc[h - 1])
                    if px <= 0:
                        continue
                    df.at[idx, f'close_{h}d'] = round(px, 4)
                    df.at[idx, f'date_{h}d'] = observation_date.date().isoformat()
                    df.at[idx, f'return_{h}d_pct'] = round((px / float(r['entry_close']) - 1) * 100, 2)
                    updated += 1
        except Exception as exc:
            print(f'Validation skipped {ticker}: {type(exc).__name__}: {exc}')
    df['entry_date'] = df['entry_date'].dt.strftime('%Y-%m-%d')
    df.to_csv(path, index=False, encoding='utf-8-sig')
    return f'Queried {queried} tickers; filled {updated} horizon observations'


if __name__ == '__main__':
    print(update_forward_returns())
