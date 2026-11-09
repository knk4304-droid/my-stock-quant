"""Korean local time presentation for timestamped data; UTC source is retained."""
from zoneinfo import ZoneInfo
import datetime as dt
import pandas as pd

KST = ZoneInfo('Asia/Seoul')

def now_kst():
    return dt.datetime.now(dt.timezone.utc).astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')

def with_kst(frame):
    """Add human-readable KST timestamp columns; never modify original UTC fields.

    Naive values in explicitly UTC-labelled columns are interpreted as UTC.
    Date-only columns are deliberately untouched (trading dates are not instants).
    """
    if not isinstance(frame, pd.DataFrame):
        return frame
    result = frame.copy()
    for col in list(result.columns):
        name = str(col)
        if name.lower() in ('기록시각_utc', 'timestamp_utc', 'recorded_at_utc'):
            target = '기록시각_KST' if name.lower() == '기록시각_utc' else name[:-3] + 'KST'
            converted = pd.to_datetime(result[col], utc=True, errors='coerce').dt.tz_convert(KST)
            result[target] = converted.dt.strftime('%Y-%m-%d %H:%M:%S KST').fillna('')
    return result
