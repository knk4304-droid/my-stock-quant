"""Compare frozen R26 top lists on identical cohorts with explicit closing prices."""
import argparse
from functools import lru_cache
import json
import math
from pathlib import Path

import pandas as pd
from exchange_calendars import get_calendar

from qp_current_gate_r60 import exchange_zone


@lru_cache(maxsize=4096)
def observation_window(ticker, captured, horizon):
    zone = exchange_zone(ticker)
    calendar = get_calendar('XKRX' if zone == 'Asia/Seoul' else 'XNYS')
    next_day = captured.tz_convert(zone).date() + pd.Timedelta(days=1)
    entry = calendar.date_to_session(next_day, direction='next')
    exit_session = calendar.session_offset(entry, horizon)
    return entry.date(), exit_session.date(), calendar.session_close(exit_session)


def compare(snapshots, prices, cutoff, horizon, fee_bps):
    """Equal-weight research baskets. Any missing constituent excludes the pair."""
    if horizon not in (1, 5, 20) or not 0 <= fee_bps <= 1000:
        raise ValueError('horizon must be 1, 5, or 20 and fee_bps must be between 0 and 1000')
    cutoff = pd.to_datetime(cutoff, utc=True)
    quotes = prices.assign(date=pd.to_datetime(prices['date'], errors='coerce').dt.date,
                           close=pd.to_numeric(prices['close'], errors='coerce').astype(float))
    # Conflicting duplicate observations cannot identify a single closing price.
    quotes = quotes.drop_duplicates().drop_duplicates(['ticker', 'date'], keep=False)
    lookup = quotes.set_index(['ticker', 'date']).close.to_dict()
    fee = fee_bps / 10_000
    rows = []
    seen = set()
    for snapshot in sorted(snapshots, key=lambda row: row['at_utc']):
        if snapshot.get('model_version') != 'R26-baseline':
            continue
        captured = pd.to_datetime(snapshot['at_utc'], utc=True)
        if captured >= cutoff or captured in seen:
            continue
        seen.add(captured)
        baseline = snapshot['periods']
        challenger = snapshot.get('challenger_periods', {})
        for period, leaders in baseline.items():
            alternative = challenger.get(period, [])
            if not leaders or len(leaders) != len(alternative):
                continue
            models = [[item['ticker'] for item in picks] for picks in (leaders, alternative)]
            if any(len(set(tickers)) != len(tickers) for tickers in models):
                continue
            price_dates = [pd.to_datetime(item.get('price_date'), errors='coerce')
                           for item in [*leaders, *alternative]]
            if any(pd.isna(day) or day.date() > captured.tz_convert(exchange_zone(item['ticker'])).date()
                   for item, day in zip([*leaders, *alternative], price_dates)):
                continue
            windows = {ticker: observation_window(ticker, captured, horizon)
                       for ticker in set(models[0] + models[1])}
            row = {'captured': captured, 'period': period, 'baseline_pct': None,
                   'challenger_pct': None, 'difference_pp': None}
            if any(close_at > cutoff for _, _, close_at in windows.values()):
                rows.append({**row, 'status': 'pending'})
                continue
            returns = {}
            for ticker, (entry, exit_day, _) in windows.items():
                start = lookup.get((ticker, entry), math.nan)
                end = lookup.get((ticker, exit_day), math.nan)
                if all(math.isfinite(value) and value > 0 for value in (start, end)):
                    returns[ticker] = 100 * (end * (1 - fee) / (start * (1 + fee)) - 1)
            if len(returns) != len(windows):
                rows.append({**row, 'status': 'missing prices'})
                continue
            base, alternate = [sum(returns[ticker] for ticker in tickers) / len(tickers)
                               for tickers in models]
            rows.append({**row, 'status': 'paired', 'baseline_pct': base,
                         'challenger_pct': alternate, 'difference_pp': alternate - base})
    return pd.DataFrame(rows, columns=['captured', 'period', 'status', 'baseline_pct',
                                       'challenger_pct', 'difference_pp'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshots', type=Path, default=Path('market_scan_data/ranking_snapshots.json'))
    parser.add_argument('--prices', type=Path, help='Adjusted daily ticker,date,close CSV, including delisted names')
    parser.add_argument('--cutoff', required=True, help='UTC timestamp of last available observations')
    parser.add_argument('--fee-bps', type=float, default=20, help='Per-side transaction cost assumption')
    args = parser.parse_args()
    prices = pd.read_csv(args.prices, dtype={'ticker': str}) if args.prices else pd.DataFrame(columns=['ticker','date','close'])
    snapshots = json.loads(args.snapshots.read_text(encoding='utf-8'))
    for horizon in (1, 5, 20):
        result = compare(snapshots, prices, args.cutoff, horizon, args.fee_bps)
        print(f'{horizon} sessions, {args.fee_bps:g} bp per side')
        print(result.groupby(['period', 'status']).size().to_string())
        paired = result[result.status.eq('paired')]
        if not paired.empty:
            print(paired.groupby('period')[['baseline_pct', 'challenger_pct', 'difference_pp']].mean().to_string())


if __name__ == '__main__':
    main()
