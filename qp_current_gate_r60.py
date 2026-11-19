"""Fail-closed validation of refreshed recommendation rows (daily bar, not tick quote)."""
from datetime import datetime, timezone
import pandas as pd
from qp_refresh_r23 import expected_weekday


def eligible_refreshed(frame, now=None):
    if frame is None or frame.empty:
        return pd.DataFrame(), {'checked': 0, 'eligible': 0, 'rejected': 0}
    now = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize('UTC')
    kept = []
    for row in frame.to_dict('records'):
        try:
            ticker = str(row['ticker'])
            domestic = ticker.upper().endswith(('.KS', '.KQ'))
            asof = pd.Timestamp(row['asof_price']).date()
            local = now.tz_convert('Asia/Seoul' if domestic else 'America/New_York').date()
            # Require latest expected weekday bar, allowing one weekday of data-provider delay.
            expected = expected_weekday(now, domestic)
            lag = int(__import__('numpy').busday_count(asof, expected))
            if asof > local or lag < 0 or lag > 1:
                continue
            stamp = pd.Timestamp(row['scanned_at_utc'])
            stamp = stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')
            if stamp > now or now - stamp > pd.Timedelta(minutes=5):
                continue
            kept.append(row)
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    return pd.DataFrame(kept, columns=frame.columns), {'checked': len(frame), 'eligible': len(kept), 'rejected': len(frame)-len(kept)}
