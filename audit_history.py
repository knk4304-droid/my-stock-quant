"""Append-only, date-deduplicated observations from the *batch* engine.

These are not the Streamlit live ranking scores. They are recorded after the
batch passes its data-quality gates. No future price is used at record time.
"""
from pathlib import Path
from zoneinfo import ZoneInfo
import datetime as dt
import pandas as pd

KST = ZoneInfo('Asia/Seoul')
SCORE_HORIZONS = ('1W', '1M', '6M', '1Y')
HORIZONS = (1, 3, 5, 10, 20)
HISTORY_COLUMNS = ['기록일_KST','기록시각_UTC','티커','종목명','시장','기준종가','가격기준일'] + [f'총점_{h}' for h in SCORE_HORIZONS]


def build_daily_observations(batch, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('timestamp must be timezone aware')
    if not {'티커','기준종가','가격기준일'}.issubset(batch.columns):
        raise ValueError('Missing ticker/price/as-of columns')
    frame = batch.copy()
    frame['기준종가'] = pd.to_numeric(frame['기준종가'], errors='coerce')
    frame['가격기준일'] = pd.to_datetime(frame['가격기준일'], errors='coerce', utc=True)
    frame = frame.dropna(subset=['티커','기준종가','가격기준일'])
    frame = frame[frame['기준종가'].gt(0)]
    frame = frame[frame['가격기준일'].le(pd.Timestamp(now))]
    frame = frame.drop_duplicates('티커', keep='first')
    frame['기록일_KST'] = now.astimezone(KST).date().isoformat()
    frame['기록시각_UTC'] = now.astimezone(dt.timezone.utc).isoformat()
    frame['가격기준일'] = frame['가격기준일'].dt.strftime('%Y-%m-%d')
    for col in HISTORY_COLUMNS:
        if col not in frame: frame[col] = pd.NA
    return frame[HISTORY_COLUMNS]


def append_daily_observations(batch, path='recommendation_history.csv', now=None):
    path = Path(path)
    fresh = build_daily_observations(batch, now)
    if fresh.empty:
        raise ValueError('No valid observations; previous archive preserved')
    if path.exists():
        old = pd.read_csv(path, dtype={'티커':'string'}, encoding='utf-8-sig')
        if not {'기록일_KST','티커'}.issubset(old.columns):
            raise ValueError('Existing history schema invalid; archive preserved')
        old = old.reindex(columns=HISTORY_COLUMNS)
        # First successfully captured observation per KST day is retained.
        combined = pd.concat([old, fresh], ignore_index=True)
    else:
        combined = fresh
    combined = combined.drop_duplicates(['기록일_KST','티커'], keep='first')
    tmp = path.with_suffix('.tmp')
    combined.to_csv(tmp, index=False, encoding='utf-8-sig')
    tmp.replace(path)
    return len(combined), len(combined)- (len(old) if path.exists() and 'old' in locals() else 0)


def evaluate_observed_history(history):
    """Compare only subsequent *observed trading dates*, not calendar days.

    Gaps in archive observations are not imputed: only actual later observed
    dates are used, so horizons are 'observed sessions', not guaranteed sessions.
    """
    required = {'기록일_KST','티커','기준종가','가격기준일'}
    if not required.issubset(history.columns):
        raise ValueError('History schema missing required columns')
    h = history.copy()
    h['기준종가'] = pd.to_numeric(h['기준종가'],errors='coerce')
    h['가격기준일'] = pd.to_datetime(h['가격기준일'], errors='coerce')
    h['기록일_KST'] = pd.to_datetime(h['기록일_KST'],errors='coerce')
    h = h.dropna(subset=['티커','기준종가','가격기준일','기록일_KST'])
    h = h[h['기준종가']>0].sort_values(['티커','가격기준일','기록일_KST'])
    # Do not count the same market close multiple times if the market was closed.
    h = h.drop_duplicates(['티커','가격기준일'], keep='first')
    output=[]
    for ticker, g in h.groupby('티커'):
        g=g.reset_index(drop=True)
        for i in range(len(g)):
            for horizon in HORIZONS:
                if i+horizon >= len(g): continue
                a,b=g.iloc[i],g.iloc[i+horizon]
                output.append({'티커':ticker,'기록일_KST':a['기록일_KST'].date().isoformat(),
                  '기간_관측거래일':horizon,'기준가격':float(a['기준종가']),
                  '평가가격':float(b['기준종가']), '평가기준일':b['가격기준일'].date().isoformat(),
                  '수익률(%)':round((float(b['기준종가'])/float(a['기준종가'])-1)*100,3),
                  '관측간격_달력일':(b['가격기준일']-a['가격기준일']).days})
    return pd.DataFrame(output,columns=['티커','기록일_KST','기간_관측거래일','기준가격','평가가격','평가기준일','수익률(%)','관측간격_달력일'])
