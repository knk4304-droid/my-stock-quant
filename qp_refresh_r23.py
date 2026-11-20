"""Bounded on-demand refresh; never writes historical recommendations."""
import re
import math
from threading import Event
from time import sleep
from concurrent.futures import ThreadPoolExecutor
import pandas as pd


class QuoteSweep:
    """Stop queued Yahoo calls after a provider-wide failure; retry a transient error once."""

    def __init__(self, fetch):
        self.fetch = fetch
        self.stopped = Event()
        self.reason = None

    def __call__(self, ticker):
        for attempt in range(2):
            if self.stopped.is_set():
                raise RuntimeError(self.reason)
            try:
                return self.fetch(ticker)
            except Exception as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                message = str(exc).casefold()
                if (type(exc).__name__ == 'YFRateLimitError' or status == 429
                        or 'too many requests' in message or 'rate limited' in message):
                    self.reason = 'Yahoo Finance 요청 제한'
                elif (status in (401, 403) or 'tunnel failed, response 403' in message
                      or '403 forbidden' in message or 'domain forbidden' in message):
                    self.reason = 'Yahoo Finance 접근 차단'
                else:
                    transient = (isinstance(exc, TimeoutError) or status in (500, 502, 503, 504)
                                 or 'timed out' in message or 'timeout' in message)
                    if transient and attempt == 0:
                        sleep(1)
                        continue
                    raise
                self.stopped.set()
                raise RuntimeError(self.reason) from exc


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


def refresh_candidates(frame, fetch, limit=20, now=None):
    """Only successful fresh candidates enter the refreshed ranking."""
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    candidates=frame.head(limit).copy(); rows=[]; failed=[]
    def one(row):
        try:
            result=fetch(str(row['ticker']))
            if not result or not all(math.isfinite(float(result[k])) for k in ('score','close','return_5d_pct','return_20d_pct','volatility_annual')): return None
            if not 0 <= float(result['score']) <= 100 or float(result['close']) <= 0 or float(result['volatility_annual']) < 0: return None
            day=pd.Timestamp(result['asof_price']).date()
            local=now.tz_convert('Asia/Seoul' if str(row['ticker']).endswith(('.KS','.KQ')) else 'America/New_York').date()
            if day>local or (local-day).days>7: return None
            return {**row,**result,'scanned_at_utc':now}
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
