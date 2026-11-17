"""Bounded on-demand refresh; never writes historical recommendations."""
import re
from concurrent.futures import ThreadPoolExecutor
import pandas as pd


def resolve_catalog(raw, catalog):
    raw=raw.strip(); normalized=re.sub(r'\s+', '', raw).casefold()
    if not normalized: return ''
    matches=set()
    for row in catalog.itertuples():
        ticker=str(row.ticker).upper()
        if normalized in {re.sub(r'\s+', '', str(row.name)).casefold(),ticker.casefold()} or (raw.isdigit() and ticker.split('.')[0]==raw):
            matches.add(ticker)
    if len(matches)==1: return matches.pop()
    if len(matches)>1: return ''
    return raw.upper() if re.fullmatch(r'[A-Za-z][A-Za-z0-9.\-]{0,14}|\d{6}\.(?:KS|KQ)',raw,re.I) else ''


def refresh_candidates(frame, fetch, limit=20):
    """Only successful fresh candidates enter the refreshed ranking."""
    candidates=frame.head(limit).copy(); rows=[]; failed=[]
    def one(row):
        try:
            result=fetch(str(row['ticker']))
            if not result or not all(pd.notna(result.get(k)) for k in ('score','close','return_5d_pct','return_20d_pct','volatility_annual','asof_price')): return None
            return {**row,**result,'scanned_at_utc':pd.Timestamp.now(tz='UTC')}
        except Exception: return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row,result in zip(candidates.to_dict('records'),pool.map(one,candidates.to_dict('records'))):
            if result is None: failed.append(row['ticker'])
            else: rows.append(result)
    return pd.DataFrame(rows,columns=candidates.columns.union(['asof_price','scanned_at_utc','close','score','return_5d_pct','return_20d_pct','volatility_annual'],sort=False)),failed


def expected_weekday(now, domestic):
    local=pd.Timestamp(now).tz_convert('Asia/Seoul' if domestic else 'America/New_York')
    day=local.normalize()
    if local.hour < (9 if domestic else 10): day-=pd.Timedelta(days=1)
    while day.weekday()>=5: day-=pd.Timedelta(days=1)
    return day.date()
