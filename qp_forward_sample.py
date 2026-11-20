"""Collect bounded, completed price windows for actual recorded recommendations."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import pandas as pd
from exchange_calendars import get_calendar

from qp_current_gate_r60 import exchange_zone
from qp_forward_compare import archived_quotes, recorded_windows
from qp_refresh_r23 import QuoteSweep


def session_days(ticker, start, end):
    market = 'XKRX' if exchange_zone(ticker) == 'Asia/Seoul' else 'XNYS'
    return {session.date() for session in get_calendar(market).sessions_in_range(start, end)}


def plan(history, observed, cutoff, limit):
    """Fetch only matured windows, once per ticker, interleaving period and market."""
    known = defaultdict(set)
    prices = observed[['ticker', 'date', 'close']].drop_duplicates()
    prices = prices.drop_duplicates(['ticker', 'date'], keep=False)
    for row in prices.itertuples(index=False):
        known[row.ticker].add(row.date)
    groups = defaultdict(dict)
    needed = defaultdict(set)
    benchmarks = defaultdict(set)
    for period, ticker, (start, end, close_at) in recorded_windows(history, cutoff):
        if close_at > cutoff:
            continue
        zone = exchange_zone(ticker)
        dates = session_days(ticker, start, end)
        missing = dates - known[ticker]
        needed[ticker].update(dates)
        if missing:
            # Prioritize windows closest to completion without consulting returns.
            group = groups[period, zone]
            group[ticker] = min(group.get(ticker, len(missing)), len(missing))
        benchmark = '^KS200' if zone == 'Asia/Seoul' else '^GSPC'
        benchmarks[benchmark].update(dates)
    # Rotate equally incomplete names daily rather than repeatedly probing the same names.
    ordinal = cutoff.date().toordinal()
    queues = []
    for group in sorted(groups):
        def priority(ticker):
            tie = hashlib.sha256(f'{ordinal}:{ticker}'.encode()).digest()
            return groups[group][ticker], tie
        queues.append(iter(sorted(groups[group], key=priority)))
    chosen = {}
    while queues and len(chosen) < limit:
        for queue in queues[:]:
            ticker = next(queue, None)
            if ticker is None:
                queues.remove(queue)
            else:
                chosen[ticker] = needed[ticker]
            if len(chosen) == limit:
                break
    return {**{ticker: days for ticker, days in benchmarks.items() if days - known[ticker]}, **chosen}


def collect(jobs, cutoff, fetch):
    def request(ticker):
        days = jobs[ticker]
        return fetch(ticker, min(days), max(days) + pd.Timedelta(days=1))

    sweep = QuoteSweep(request)
    rows, failures = [], {}
    for ticker, expected in jobs.items():
        if sweep.stopped.is_set():
            break
        try:
            bars = sweep(ticker)
            raw = pd.to_numeric(bars['Close'], errors='coerce')
            index = pd.DatetimeIndex(raw.index)
            if index.tz is not None:
                index = index.tz_convert(exchange_zone(ticker))
            quotes = pd.DataFrame({'date': index.date, 'close': raw.to_numpy()})
            quotes = quotes[quotes.date.isin(expected) & quotes.close.gt(0) & quotes.close.lt(float('inf'))]
            quotes = quotes.drop_duplicates().drop_duplicates('date', keep=False)
            rows.extend((ticker, day, price) for day, price in quotes.itertuples(index=False, name=None))
            if len(quotes) < len(expected):
                failures[ticker] = f'missing {len(expected) - len(quotes)} of {len(expected)} closes'
        except Exception as exc:
            failures[ticker] = sweep.reason or type(exc).__name__
    result = pd.DataFrame(rows, columns=['ticker', 'date', 'close'])
    return result, {'checked_at': cutoff.isoformat(), 'planned_tickers': len(jobs),
                    'observed_tickers': result.ticker.nunique(), 'provider_stop_reason': sweep.reason,
                    'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cutoff', required=True, help='UTC evaluation timestamp')
    parser.add_argument('--max-tickers', type=int, default=24)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.max_tickers <= 40:
        parser.error('max-tickers must be between 1 and 40')

    import yfinance as yf

    def fetch(ticker, start, end):
        return yf.Ticker(ticker).history(start=str(start), end=str(end), auto_adjust=True,
                                         interval='1d', timeout=10, raise_errors=True)

    now = pd.to_datetime(args.cutoff, utc=True, errors='coerce')
    if pd.isna(now) or now > pd.Timestamp.now(tz='UTC'):
        parser.error('cutoff must be a valid past or current timestamp')
    history = pd.read_csv('market_scan_data/recommendation_history.csv', dtype={'ticker': str})
    observations = pd.read_csv('market_scan_data/observations.csv', dtype={'ticker': str})
    observed = archived_quotes(observations, now)
    prices, report = collect(plan(history, observed, now, args.max_tickers), now, fetch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(args.output, index=False)
    args.output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
