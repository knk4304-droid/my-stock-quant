"""Descriptive validation of forward recommendation outcomes.

This module deliberately does NOT report a statistically proven trading edge.
Repeated picks and shared market days are correlated; date-cluster bootstrap is
used for a conservative diagnostic interval, not a formal predictive guarantee.
"""
from pathlib import Path
import numpy as np
import pandas as pd

HORIZONS=(1,5,20)
REQUIRED={'ticker','period','entry_date','entry_close'}

def evaluate(frame, horizon=5, n_boot=1000, seed=2026):
    if horizon not in HORIZONS: raise ValueError('Unsupported horizon')
    col=f'return_{horizon}d_pct'
    if not REQUIRED.issubset(frame.columns):
        return {'status':'자료 형식 오류','total':len(frame),'observed':0}
    d=frame.copy()
    if col not in d: d[col]=np.nan
    d['entry_date']=pd.to_datetime(d['entry_date'],errors='coerce').dt.normalize()
    d['entry_close']=pd.to_numeric(d['entry_close'],errors='coerce')
    d[col]=pd.to_numeric(d[col],errors='coerce').replace([np.inf,-np.inf],np.nan)
    d=d.dropna(subset=['ticker','period','entry_date','entry_close'])
    d=d[d.entry_close.gt(0)]
    # Each distinct date+period+ticker is a recommendation; repeated records are not independent observations.
    d=d.drop_duplicates(['entry_date','period','ticker'],keep='first')
    total=len(d)
    v=d.dropna(subset=[col]).copy()
    n=len(v)
    result={'status':'자료 부족','total':total,'observed':n,'coverage_pct':round(100*n/total,1) if total else 0,
            'days':int(v.entry_date.nunique()) if n else 0,'tickers':int(v.ticker.nunique()) if n else 0}
    if not n:return result
    x=v[col].to_numpy(float)
    result.update(mean_pct=round(float(np.mean(x)),2),median_pct=round(float(np.median(x)),2),
                  win_rate_pct=round(float(np.mean(x>0)*100),1),
                  min_pct=round(float(np.min(x)),2),max_pct=round(float(np.max(x)),2))
    # Only complete, sufficiently varied samples qualify for interval diagnostics.
    if n<30 or result['days']<10 or result['tickers']<10 or result['coverage_pct']<70:
        return result
    by_day=[g[col].to_numpy(float) for _,g in v.groupby('entry_date')]
    rng=np.random.default_rng(seed)
    means=np.empty(n_boot)
    for i in range(n_boot):
        sampled=rng.integers(0,len(by_day),len(by_day))
        means[i]=np.concatenate([by_day[j] for j in sampled]).mean()
    lo,hi=np.percentile(means,[2.5,97.5])
    result.update(status='탐색적 통계 확인',ci_low_pct=round(float(lo),2),ci_high_pct=round(float(hi),2))
    return result

def audit(frame):
    issues=[]
    if not REQUIRED.issubset(frame.columns):return ['필수 추천 기록 열 누락']
    d=frame.copy()
    d['entry_date']=pd.to_datetime(d['entry_date'],errors='coerce')
    for h in HORIZONS:
        dc=f'date_{h}d';rc=f'return_{h}d_pct';pc=f'close_{h}d'
        if dc not in d or rc not in d:continue
        obs=pd.to_datetime(d[dc],errors='coerce')
        ret=pd.to_numeric(d[rc],errors='coerce')
        invalid=(obs.notna() & (obs<=d.entry_date))
        if invalid.any():issues.append(f'{h}거래일: 추천일 이전 또는 당일 결과 {int(invalid.sum())}건')
        if (ret.notna() & obs.isna()).any():issues.append(f'{h}거래일: 관측일 없는 수익률')
        if pc in d:
            px=pd.to_numeric(d[pc],errors='coerce')
            entry=pd.to_numeric(d['entry_close'],errors='coerce')
            mismatch=ret.notna() & px.gt(0) & entry.gt(0) & ((px/entry-1)*100-ret).abs().gt(.08)
            if mismatch.any():issues.append(f'{h}거래일: 가격과 수익률 불일치 {int(mismatch.sum())}건')
    return issues

def report(path):
    path=Path(path)
    if not path.exists():return {'status':'추천 기록 없음','issues':[],'horizons':{}}
    df=pd.read_csv(path,dtype={'ticker':str})
    return {'status':'확인','issues':audit(df),'horizons':{h:evaluate(df,h) for h in HORIZONS}}
