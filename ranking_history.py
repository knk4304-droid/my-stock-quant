"""Immutable per-run recommendation ranking snapshots, saved by GitHub Actions."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import pandas as pd

KST = timezone(timedelta(hours=9))
PERIODS = ['단기 (1~3일)', '스윙 (1~2주)', '중기 (1~3개월)', '장기 (1년 이상)']


def ranking(frame, period):
    from qp_rank_r26 import rank as shared_rank
    return shared_rank(frame, period)


def record_snapshot(data_dir, *, now=None):
    data_dir = Path(data_dir)
    scores_file = data_dir / 'scores.csv'
    if not scores_file.exists():
        return False
    scores = pd.read_csv(scores_file, dtype={'ticker': str})
    if scores.empty or 'scanned_at_utc' not in scores:
        return False
    now = now or datetime.now(timezone.utc)
    scan_times = pd.to_datetime(scores['scanned_at_utc'], utc=True, errors='coerce')
    age = (pd.Timestamp(now) - scan_times).dt.total_seconds() / 86400
    fresh = scores.loc[age.between(0, 7)].copy()
    fresh['_scan_time'] = scan_times.loc[fresh.index]
    fresh = fresh.sort_values('_scan_time').drop_duplicates('ticker', keep='last')
    from qp_discovery_r25 import valid_prices
    fresh=valid_prices(fresh,now)
    if fresh.empty:
        return False
    history_file = data_dir / 'ranking_snapshots.json'
    try:
        history = json.loads(history_file.read_text(encoding='utf-8')) if history_file.exists() else []
    except (ValueError, OSError):
        history = []
    # One run creates one snapshot. Existing entries are never rewritten.
    stamp = now.astimezone(timezone.utc).isoformat(timespec='seconds')
    snapshot = {'at_utc': stamp, 'candidate_count': len(fresh), 'periods': {}, 'model_version':'R26-baseline', 'challenger_periods': {}}
    for period in PERIODS:
        from qp_rank_r26 import rank as shared_rank
        shadow=shared_rank(fresh,period,challenger=True).head(10)
        snapshot['challenger_periods'][period]=[{'ticker':str(r.ticker),'score':float(r.ranking_score),'price_date':str(r.asof_price),'close':float(r.close)} for r in shadow.itertuples()]
        top = ranking(fresh, period).head(10)
        snapshot['periods'][period] = [
            {'rank': i, 'ticker': str(row['ticker']), 'name': str(row.get('name', '')),
             'score': float(row['ranking_score']), 'market': str(row.get('market', '')),
             'price_date': str(row.get('asof_price', '')),
             'scanned_at_utc': row['_scan_time'].isoformat() if pd.notna(row['_scan_time']) else ''}
            for i, (_, row) in enumerate(top.iterrows(), 1)
        ]
    history.append(snapshot)
    # Keep the full current and preceding 11 KST weeks; older records can be archived separately.
    cutoff = (now.astimezone(KST) - timedelta(weeks=12)).date().isoformat()
    history = [h for h in history if h.get('at_utc') and h['at_utc'][:10] >= cutoff]
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
    return True


if __name__ == '__main__':
    record_snapshot(Path(__file__).resolve().parent / 'market_scan_data')
