"""Display-only intraday index quotes; never feed partial bars into rankings."""
import pandas as pd
from qp_current_gate_r60 import exchange_zone, latest_completed_session, completed_bars

def index_quote(ticker, fetch, now=None):
    now = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now).tz_convert('UTC')
    zone = exchange_zone(ticker)
    def clean(frame):
        s = pd.to_numeric(frame['Close'], errors='coerce').dropna().sort_index()
        return s[s.gt(0) & s.lt(float('inf'))]
    daily = clean(completed_bars(fetch(period='10d', interval='1d'), ticker, now))
    if daily.empty: raise ValueError('종가 미확보')
    day = daily.index[-1].date()
    expected = latest_completed_session(ticker, now)
    price = float(daily.iloc[-1]); change = 100*(price/float(daily.iloc[-2])-1) if len(daily)>1 else None
    status = '최근 확정 일봉' if day == expected else '지연 · 이전 종가'
    asof = str(day)
    try:
        from exchange_calendars import get_calendar
        cal = get_calendar('XKRX' if zone=='Asia/Seoul' else 'XNYS')
        local_day = now.tz_convert(zone).date()
        session = cal.date_to_session(local_day, direction='none')
        if cal.session_open(session) <= now < cal.session_close(session):
            status = '장중 지수 미확보 · 이전 종가'
            bars = clean(fetch(period='1d', interval='5m'))
            if not bars.empty and bars.index.tz is not None:
                stamp = bars.index[-1].tz_convert('UTC')
                if cal.session_open(session) <= stamp <= now and day == expected:
                    price = float(bars.iloc[-1]); change = 100*(price/float(daily.iloc[-1])-1)
                    asof = stamp.tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M KST')
                    status = '장중 5분봉 · 지연 가능' if now-stamp <= pd.Timedelta(minutes=20) else '장중 5분봉 · 지연'
    except Exception:
        pass
    return price, change, asof, status
