"""Compare frozen R26 top lists on identical cohorts with explicit closing prices."""
import argparse
from functools import lru_cache
import json
import math
from pathlib import Path

import pandas as pd
from exchange_calendars import get_calendar

from benchmark_review_v70 import benchmark_for_ticker
from qp_current_gate_r60 import exchange_zone


@lru_cache(maxsize=4096)
def observation_window(ticker, captured, horizon):
    zone = exchange_zone(ticker)
    calendar = get_calendar('XKRX' if zone == 'Asia/Seoul' else 'XNYS')
    next_day = captured.tz_convert(zone).date() + pd.Timedelta(days=1)
    entry = calendar.date_to_session(next_day, direction='next')
    exit_session = calendar.session_offset(entry, horizon)
    return entry.date(), exit_session.date(), calendar.session_close(exit_session)


def basket_path(tickers, windows, lookup, fee):
    """Daily local-close marks for an equal-weight cohort, expressed in local returns."""
    paths = []
    for ticker in tickers:
        entry, exit_day, _ = windows[ticker]
        calendar = get_calendar('XKRX' if exchange_zone(ticker) == 'Asia/Seoul' else 'XNYS')
        days = [session.date() for session in calendar.sessions_in_range(entry, exit_day)]
        closes = [lookup.get((ticker, day), math.nan) for day in days]
        if not all(math.isfinite(close) and close > 0 for close in closes):
            return None
        values = [close / (closes[0] * (1 + fee)) for close in closes]
        values[-1] *= 1 - fee
        paths.append(pd.Series(values, index=days))
    # A closed market or a sleeve that has exited keeps its previous value.
    # A sleeve awaiting entry starts in cash. Missing open-session quotes were rejected above.
    marks = pd.concat(paths, axis=1).sort_index().ffill().fillna(1).mean(axis=1)
    return pd.concat([pd.Series([1.0]), marks], ignore_index=True)


def maximum_drawdown(path):
    return 100 * (1 - path.div(path.cummax())).max()


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
            row = dict.fromkeys(('baseline_pct', 'challenger_pct', 'difference_pp', 'benchmark_pct',
                                 'baseline_mdd_pct', 'challenger_mdd_pct', 'benchmark_mdd_pct'))
            row.update(captured=captured, period=period)
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
            row.update(status='paired', baseline_pct=base, challenger_pct=alternate,
                       difference_pp=alternate - base)
            for label, tickers in zip(('baseline', 'challenger'), models):
                path = basket_path(tickers, windows, lookup, fee)
                if path is not None:
                    row[f'{label}_mdd_pct'] = maximum_drawdown(path)
            # The same benchmark uses the combined country weights of both frozen lists.
            benchmarks = [benchmark_for_ticker(ticker) for tickers in models for ticker in tickers]
            benchmark_windows = {ticker: observation_window(ticker, captured, horizon)
                                 for ticker in set(benchmarks)}
            benchmark = basket_path(benchmarks, benchmark_windows, lookup, 0)
            if benchmark is not None:
                row.update(benchmark_pct=100 * (benchmark.iloc[-1] - 1),
                           benchmark_mdd_pct=maximum_drawdown(benchmark))
            rows.append(row)
    return pd.DataFrame(rows, columns=['captured', 'period', 'status', 'baseline_pct',
                                       'challenger_pct', 'difference_pp', 'benchmark_pct',
                                       'baseline_mdd_pct', 'challenger_mdd_pct', 'benchmark_mdd_pct'])


def archived_quotes(observations, cutoff):
    """Recover known closing prices from timed scan observations."""
    cutoff = pd.to_datetime(cutoff, utc=True)
    parts = []
    for side in ('old', 'new'):
        parts.append(observations[['ticker', f'asof_price_{side}', f'close_{side}', f'scanned_at_utc_{side}']]
                     .set_axis(['ticker', 'date', 'close', 'seen_at'], axis=1))
    quotes = pd.concat(parts, ignore_index=True).drop_duplicates()
    quotes['seen_at'] = pd.to_datetime(quotes['seen_at'], format='mixed', utc=True, errors='coerce')
    quotes['date'] = pd.to_datetime(quotes['date'], errors='coerce').dt.date
    quotes['close'] = pd.to_numeric(quotes['close'], errors='coerce')
    eligible = quotes.loc[quotes.seen_at.le(cutoff) & quotes.date.notna() & quotes.close.gt(0)
                          & quotes.close.lt(float('inf'))]
    rows = []
    for quote in eligible.itertuples(index=False):
        calendar = get_calendar('XKRX' if exchange_zone(quote.ticker) == 'Asia/Seoul' else 'XNYS')
        if calendar.is_session(quote.date) and calendar.session_close(quote.date) <= quote.seen_at:
            rows.append((quote.ticker, quote.date, quote.close))
    return pd.DataFrame(rows, columns=['ticker', 'date', 'close']).drop_duplicates()


RECOMMENDATION_HORIZONS = {'단기': 1, '스윙': 5, '중기': 20}


def recorded_cases(history, cutoff):
    # Use the CSV data-row position so each audit line can be traced to its input.
    history = history.assign(source_row=range(1, len(history) + 1),
                             captured=pd.to_datetime(history.recorded_at_utc, format='mixed', utc=True,
                                                     errors='coerce')).sort_values('captured', kind='stable')
    first_rows = {}
    for record in history.itertuples(index=False):
        ticker, captured = record.ticker, record.captured
        period = str(record.period).split(' ', 1)[0]
        horizon = RECOMMENDATION_HORIZONS.get(period)
        market = '미확인'
        window = None
        duplicate_of = None
        if not isinstance(ticker, str) or not ticker.strip() or pd.isna(captured):
            status = 'invalid record'
        else:
            ticker = ticker.strip().upper()
            zone = exchange_zone(ticker)
            market = 'KR' if zone == 'Asia/Seoul' else 'US'
            key = period, ticker, captured.tz_convert(zone).date()
            if horizon is None:
                status = 'outside evaluation periods'
            elif captured >= cutoff:
                status = 'not available at cutoff'
            elif key in first_rows:
                status = 'duplicate local day'
                duplicate_of = first_rows[key]
            else:
                first_rows[key] = record.source_row
                try:
                    window = observation_window(ticker, captured, horizon)
                except ValueError:
                    status = 'calendar unavailable'
                else:
                    status = 'pending' if window[2] > cutoff else 'mature'
        yield {'source_row': record.source_row, 'captured_at_utc': captured, 'period': period,
               'market': market, 'ticker': ticker, 'status': status, 'holding_sessions': horizon,
               'duplicate_of': duplicate_of}, window


def recorded_windows(history, cutoff):
    for case, window in recorded_cases(history, cutoff):
        if window is not None:
            yield case['period'], case['ticker'], window


def compare_recorded_recommendations(history, prices, cutoff, fee_bps):
    """Reprice recorded recommendations using only later exchange-session closes."""
    if not 0 <= fee_bps <= 1000:
        raise ValueError('fee_bps must be between 0 and 1000')
    cutoff = pd.to_datetime(cutoff, utc=True)
    prices = prices.assign(date=pd.to_datetime(prices.date, errors='coerce').dt.date,
                           close=pd.to_numeric(prices.close, errors='coerce').astype(float))
    prices = prices.loc[prices.date.notna() & prices.close.gt(0) & prices.close.lt(float('inf')),
                        ['ticker', 'date', 'close']].drop_duplicates()
    conflicts = set(prices.loc[prices.duplicated(['ticker', 'date'], keep=False), ['ticker', 'date']]
                    .itertuples(index=False, name=None))
    prices = prices.drop_duplicates(['ticker', 'date'], keep=False)
    lookup = prices.set_index(['ticker', 'date']).close.to_dict()
    fee = fee_bps / 10_000
    rows = []
    for row, window in recorded_cases(history, cutoff):
        ticker, market = row['ticker'], row['market']
        row.update(entry=window[0] if window else None, exit=window[1] if window else None,
                   exit_close_at_utc=window[2] if window else None, gross_return_pct=None,
                   return_pct=None, cost_pp=None, mdd_pct=None, benchmark_pct=None, benchmark_mdd_pct=None)
        if row['status'] == 'mature':
            path = basket_path([ticker], {ticker: window}, lookup, fee)
            if path is not None:
                gross = 100 * (lookup[ticker, window[1]] / lookup[ticker, window[0]] - 1)
                net = 100 * (path.iloc[-1] - 1)
                row.update(status='observed', gross_return_pct=gross, return_pct=net,
                           cost_pp=gross - net, mdd_pct=maximum_drawdown(path))
                benchmark = '^KS200' if market == 'KR' else '^GSPC'
                index = basket_path([benchmark], {benchmark: window}, lookup, 0)
                if index is not None:
                    row.update(benchmark_pct=100 * (index.iloc[-1] - 1), benchmark_mdd_pct=maximum_drawdown(index))
            else:
                calendar = get_calendar('XKRX' if market == 'KR' else 'XNYS')
                required = {(ticker, day.date()) for day in calendar.sessions_in_range(window[0], window[1])}
                available = required.intersection(lookup)
                if required & conflicts:
                    row['status'] = 'conflicting closes'
                elif not available:
                    row['status'] = 'no window prices'
                elif (ticker, window[0]) not in lookup or (ticker, window[1]) not in lookup:
                    row['status'] = 'missing entry or exit'
                else:
                    row['status'] = 'missing intermediate closes'
        rows.append(row)
    columns = ['source_row', 'captured_at_utc', 'period', 'market', 'ticker', 'status',
               'holding_sessions', 'duplicate_of', 'entry', 'exit', 'exit_close_at_utc',
               'gross_return_pct', 'return_pct', 'cost_pp', 'mdd_pct', 'benchmark_pct', 'benchmark_mdd_pct']
    result = pd.DataFrame(rows, columns=columns)
    result[['holding_sessions', 'duplicate_of']] = result[['holding_sessions', 'duplicate_of']].astype('Int64')
    return result.sort_values('source_row', ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshots', type=Path, default=Path('market_scan_data/ranking_snapshots.json'))
    parser.add_argument('--prices', type=Path, help='Adjusted daily ticker,date,close CSV including delisted names and ^KS11/^GSPC benchmark closes')
    parser.add_argument('--recommendations', type=Path, help='Recorded recommendation history CSV')
    parser.add_argument('--audit-csv', type=Path, help='Write one traceable evaluation row per input recommendation')
    parser.add_argument('--observations', type=Path, help='Timed observation CSV with scan price provenance')
    parser.add_argument('--cutoff', required=True, help='UTC timestamp of last available observations')
    parser.add_argument('--fee-bps', type=float, default=20, help='Per-side transaction cost assumption')
    args = parser.parse_args()
    if args.audit_csv and not args.recommendations:
        parser.error('--audit-csv requires --recommendations')
    if args.audit_csv and any(args.audit_csv.resolve() == source.resolve()
                              for source in (args.recommendations, args.prices, args.observations) if source):
        parser.error('--audit-csv must not overwrite an input')
    prices = pd.read_csv(args.prices, dtype={'ticker': str}) if args.prices else pd.DataFrame(columns=['ticker','date','close'])
    if args.recommendations:
        history = pd.read_csv(args.recommendations, dtype={'ticker': str})
        if args.observations:
            observations = pd.read_csv(args.observations, dtype={'ticker': str})
            archived = archived_quotes(observations, args.cutoff)
            # Avoid splicing independently adjusted price histories for the same ticker.
            prices = pd.concat([prices, archived.loc[~archived.ticker.isin(prices.ticker)]], ignore_index=True)
        result = compare_recorded_recommendations(history, prices, args.cutoff, args.fee_bps)
        print(f'Recorded recommendations, one position per ticker/period/local day, {args.fee_bps:g} bp per side')
        if args.audit_csv:
            result.to_csv(args.audit_csv, index=False)
        statuses = result.groupby('status', dropna=False).size()
        print(f'Input rows: {len(history)}; classified rows: {statuses.sum()}')
        print(statuses.to_string())
        print(result.groupby(['period', 'market', 'status']).size().to_string())
        observed = result[result.status.eq('observed')].copy()
        if not observed.empty:
            observed['win'] = 100 * observed.return_pct.gt(0)
            print(observed.groupby('period').agg(samples=('return_pct', 'count'), mean_pct=('return_pct', 'mean'),
                                                 gross_pct=('gross_return_pct', 'mean'), cost_pp=('cost_pp', 'mean'),
                                                 win_pct=('win', 'mean'), worst_mdd_pct=('mdd_pct', 'max'),
                                                 first_entry=('entry', 'min'), last_exit=('exit', 'max')).to_string())
        matched = observed.dropna(subset=['benchmark_pct']).copy()
        matched['excess_pp'] = matched.return_pct - matched.benchmark_pct
        if not matched.empty:
            print('Matched index cohorts, descriptive only')
            print(matched.groupby('period').agg(samples=('benchmark_pct', 'count'),
                                                return_pct=('return_pct', 'mean'),
                                                benchmark_pct=('benchmark_pct', 'mean'),
                                                excess_pp=('excess_pp', 'mean'),
                                                benchmark_worst_mdd_pct=('benchmark_mdd_pct', 'max')).to_string())
        return
    snapshots = json.loads(args.snapshots.read_text(encoding='utf-8'))
    for horizon in (1, 5, 20):
        result = compare(snapshots, prices, args.cutoff, horizon, args.fee_bps)
        print(f'{horizon} sessions, {args.fee_bps:g} bp per side')
        print(result.groupby(['period', 'status']).size().to_string())
        paired = result[result.status.eq('paired')]
        if not paired.empty:
            print(paired.groupby('period')[['baseline_pct', 'challenger_pct', 'difference_pp']].mean().to_string())
            risk_cols = ['baseline_mdd_pct', 'challenger_mdd_pct', 'benchmark_mdd_pct']
            print('Worst daily-close drawdown across cohorts (%); unavailable when a session is missing')
            print(paired.groupby('period')[risk_cols].agg(['count', 'max']).to_string())
            matched = paired.dropna(subset=['benchmark_pct'])
            if not matched.empty:
                print('Mean returns on matched benchmark cohorts (%); benchmarks are fee-free indexes')
                print(matched.groupby('period')[['baseline_pct', 'challenger_pct', 'benchmark_pct']].mean().to_string())


if __name__ == '__main__':
    main()
