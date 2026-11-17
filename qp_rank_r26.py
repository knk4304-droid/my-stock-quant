"""Shared deterministic ranking; challenger is research-only until forward validation."""
import numpy as np
import pandas as pd
VERSION='R26-baseline'
FIELDS=['score','return_5d_pct','return_20d_pct','volatility_annual']
def rank(frame,period,entry=False,challenger=False):
    d=frame.copy()
    for k in FIELDS: d[k]=pd.to_numeric(d[k],errors='coerce') if k in d else np.nan
    d=d.loc[np.isfinite(d[FIELDS]).all(axis=1)&d.score.between(0,100)&d.volatility_annual.ge(0)].copy()
    r5=d.return_5d_pct.clip(-25,25); r20=d.return_20d_pct.clip(-40,40); v=d.volatility_annual.clip(0,3); t=d.score
    if period.startswith('단기'): s=.5*t+.8*r5-12*v
    elif period.startswith('스윙'): s=.6*t+.35*r5+.25*r20-10*v
    elif period.startswith('중기'): s=.7*t+.35*r20-10*v
    else: s=.8*t+.15*r20-18*v
    if challenger:
        # Remove explicit duplicated 20-day return; reward acceleration and penalize extremes.
        accel=(r5-r20/4).clip(-10,10)
        w=1 if period.startswith('단기') else .6 if period.startswith('스윙') else .25 if period.startswith('중기') else 0
        s=t+w*accel-8*v-1.5*(r5-8).clip(lower=0)-(-r5-7).clip(lower=0)
    d['추천 참고점수']=s.round(1); d['ranking_score']=d['추천 참고점수']; d['점수 입력 완전성']='4/4'
    if entry:
        r=d.return_5d_pct.clip(-20,20)
        d['매수관찰점수']=(.45*t+.6*r+.2*d.return_20d_pct.clip(-30,30)-12*v-1.5*(r-5).clip(lower=0)).round(2)
        d['진입조건충족']=d.return_5d_pct.between(-7,8,inclusive='left')
    keys=['진입조건충족','매수관찰점수','추천 참고점수'] if entry else ['추천 참고점수']
    if 'ticker' in d: keys.append('ticker')
    return d.sort_values(keys,ascending=[k=='ticker' for k in keys],kind='mergesort')
