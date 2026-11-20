"""Require the latest completed exchange session for current daily-bar analysis."""
from functools import lru_cache

import pandas as pd


def exchange_zone(ticker):
    domestic = str(ticker).upper().endswith(('.KS', '.KQ')) or ticker in ('^KS11', '^KQ11')
    return 'Asia/Seoul' if domestic else 'America/New_York'


@lru_cache(maxsize=128)
def _session_at(calendar_name, minute):
    from exchange_calendars import get_calendar

    calendar = get_calendar(calendar_name)
    local_day = minute.tz_convert(calendar.tz).date()
    session = calendar.date_to_session(local_day, direction='previous')
    if calendar.session_close(session) > minute:
        session = calendar.previous_session(session)
    return session.date()


def latest_completed_session(ticker, now=None):
    stamp = pd.to_datetime(now, utc=True) if now is not None else pd.Timestamp.now(tz='UTC')
    market = 'XKRX' if exchange_zone(ticker) == 'Asia/Seoul' else 'XNYS'
    return _session_at(market, stamp.floor('min'))


def completed_bars(frame, ticker, now=None):
    """Discard partial and future daily bars using the exchange's local session dates."""
    session = latest_completed_session(ticker, now)
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_convert(exchange_zone(ticker)).tz_localize(None)
    return frame.loc[index.normalize() <= pd.Timestamp(session)].sort_index()


def has_current_price(ticker, asof, now=None):
    try:
        day = pd.to_datetime(asof, errors='coerce')
        return bool(ticker) and pd.notna(day) and day.date() == latest_completed_session(ticker, now)
    except (ValueError, TypeError, OverflowError):
        return False


def eligible_refreshed(frame, now=None):
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy(), {'checked': 0, 'eligible': 0, 'rejected': 0}
    now = pd.to_datetime(now, utc=True) if now is not None else pd.Timestamp.now(tz='UTC')
    stamps = pd.to_datetime(frame.get('scanned_at_utc', pd.Series(index=frame.index, dtype=object)),
                            format='mixed', utc=True, errors='coerce')
    recent = stamps.between(now - pd.Timedelta(minutes=5), now)
    current = [has_current_price(row.get('ticker'), row.get('asof_price'), now)
               for row in frame.to_dict('records')]
    kept = frame.loc[recent & pd.Series(current, index=frame.index)].copy()
    return kept, {'checked': len(frame), 'eligible': len(kept), 'rejected': len(frame) - len(kept)}
