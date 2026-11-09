"""Evaluate point-in-time recommendations against later observed closing prices.

Inputs: snapshot CSV from v4.6, price CSV with ticker,date,close columns.
This is a descriptive forward-return report, not a validated trading backtest.
"""
import pandas as pd

HORIZONS = {'1~3D': 3, '1~2W': 10, '1~3M': 63, '1Y+': 252}


def evaluate(snapshot, prices, fee_bps=0):
    required_snap = {'기록시각_UTC', '티커'}
    required_prices = {'ticker', 'date', 'close'}
    if not required_snap.issubset(snapshot.columns):
        raise ValueError('추천 CSV에는 기록시각_UTC, 티커 열이 필요합니다')
    if not required_prices.issubset(prices.columns):
        raise ValueError('가격 CSV에는 ticker, date, close 열이 필요합니다')
    if not 0 <= fee_bps <= 1000:
        raise ValueError('거래비용은 0~1000bp 범위여야 합니다')
    snaps = snapshot.copy()
    snaps['timestamp'] = pd.to_datetime(snaps['기록시각_UTC'], utc=True, errors='coerce')
    quotes = prices.copy()
    quotes['timestamp'] = pd.to_datetime(quotes['date'], utc=True, errors='coerce')
    quotes['close'] = pd.to_numeric(quotes['close'], errors='coerce')
    quotes = quotes.dropna(subset=['ticker','timestamp','close'])
    quotes = quotes[quotes['close'] > 0].sort_values('timestamp').drop_duplicates(['ticker','timestamp'], keep='last')
    results = []
    for _, row in snaps.dropna(subset=['티커','timestamp']).iterrows():
        ticker = str(row['티커'])
        history = quotes[(quotes['ticker'].astype(str) == ticker) & (quotes['timestamp'] > row['timestamp'])]
        # The first close strictly AFTER the snapshot is the reference price.
        # This avoids looking backward at a possibly stale price.
        if history.empty:
            continue
        entry = float(history.iloc[0]['close'])
        for period, sessions in HORIZONS.items():
            # A horizon requires sessions subsequent closes after entry.
            if len(history) <= sessions:
                continue
            future = float(history.iloc[sessions]['close'])
            gross = (future / entry - 1) * 100
            record = {'티커':ticker, '기록시각_UTC':row['기록시각_UTC'], '기간':period,
                      '기준가격':entry, '평가가격':future,
                      '실현전수익률(%)':round(gross, 3),
                      '비용반영수익률(%)':round(gross - 2*fee_bps/100, 3),
                      '평가기준일':str(history.iloc[sessions]['timestamp'].date())}
            estimate = row.get('모형추정치_'+period)
            if pd.notna(estimate):
                record['모형추정치(%)'] = float(estimate)
                record['추정오차(%p)'] = round(float(estimate) - gross, 3)
            results.append(record)
    return pd.DataFrame(results)
