"""Candidate discovery without arbitrary repeat penalties or historical rewrites."""
import pandas as pd

def candidate_pool(full, limit=60):
    if full.empty: return full.copy()
    d=full.drop_duplicates('ticker').copy()
    d['_r5']=pd.to_numeric(d.return_5d_pct,errors='coerce')
    d['_r20']=pd.to_numeric(d.return_20d_pct,errors='coerce')
    d['_accel']=d._r5-d._r20/4
    d['_time']=pd.to_datetime(d.scanned_at_utc,utc=True,errors='coerce')
    # Preserve leaders; reserve space for near leaders, accelerating and recently scanned candidates.
    parts=[d.head(20),d.iloc[20:40],d.iloc[40:].sort_values('_accel',ascending=False).head(10),d.iloc[40:].sort_values('_time',ascending=False).head(10)]
    picked=pd.concat(parts).drop_duplicates('ticker')
    picked=pd.concat([picked,d]).drop_duplicates('ticker').head(limit)
    return picked.drop(columns=['_r5','_r20','_accel','_time'])

def valid_prices(frame, now=None):
    if frame.empty: return frame.copy()
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    d=frame.copy(); fields=['score','close','return_5d_pct','return_20d_pct','volatility_annual']
    for k in fields: d[k]=pd.to_numeric(d[k],errors='coerce')
    import numpy as np
    good=np.isfinite(d[fields]).all(axis=1)&d.score.between(0,100)&d.close.gt(0)&d.volatility_annual.ge(0)
    dates=pd.to_datetime(d.asof_price,errors='coerce').dt.date
    domestic=d.ticker.astype(str).str.endswith(('.KS','.KQ'))
    for mask,zone in [(domestic,'Asia/Seoul'),(~domestic,'America/New_York')]:
        day=now.tz_convert(zone).date()
        # Four calendar days tolerates ordinary weekends; longer holidays may reduce coverage.
        good &= ~mask | dates.between(day-pd.Timedelta(days=4),day)
    return d.loc[good].copy()
