"""Experimental OHLCV pattern scores. Not calibrated probabilities."""
import numpy as np
import pandas as pd

MODES={'반등유망순':'rebound','눌림목매수유망순':'pullback','추세돌파유망순':'breakout'}
FIELDS=['rebound','pullback','breakout']
def features(h):
    if not {'Close','High','Low','Volume'}.issubset(h.columns) or len(h)<65: return dict.fromkeys(FIELDS+['entry_judgment'],float('nan'))
    d=h[['Close','High','Low','Volume']].apply(pd.to_numeric,errors='coerce').tail(65)
    if not np.isfinite(d).all().all() or (d[['Close','High','Low']]<=0).any().any() or (d.Volume<0).any(): return {}
    c=d.Close; p=c.iloc[-1]; prev=c.iloc[-2]; m20=c.tail(20).mean(); m60=c.tail(60).mean()
    atr=(d.High-d.Low).tail(14).mean()
    if atr<=0 or d.Volume.iloc[-21:-1].mean()<=0: return {}
    support=d.Low.iloc[-21:-1].min(); resistance=d.High.iloc[-21:-1].max()
    dd=1-p/d.High.max(); adjust=1-p/d.High.tail(10).max()
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); loss=-delta.clip(upper=0).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+gain/loss.replace(0,np.nan)); macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); hist=macd-macd.ewm(span=9,adjust=False).mean()
    if not np.isfinite(rsi.iloc[-4:]).all(): return {}
    clip=lambda x:float(np.clip(x,0,1))
    recovery=clip((rsi.iloc[-1]-rsi.iloc[-4])/10)*.5+clip((hist.iloc[-1]-hist.iloc[-4])/atr)*.5
    volume=clip((d.Volume.iloc[-1]/d.Volume.iloc[-21:-1].mean()-.7)/1.3)
    risk=lambda stop,target:clip(((target-p)/max(p-stop,atr*.5))/3) if stop<p<target else 0
    out={}
    if .10<=dd<=.40 and p>=support and p-support<=3*atr and p>prev and recovery>0:
        out['rebound']=20*clip(dd/.25)+25*clip(1-(p-support)/(3*atr))+25*recovery+10*volume+20*risk(support-atr*.5,resistance)
    if m20>m60 and m20>c.iloc[-25:-5].mean() and .02<=adjust<=.15 and abs(p-m20)<=2*atr and p>prev and recovery>0:
        out['pullback']=25*clip((m20/m60-1)/.12)+20*clip(1-abs(p-m20)/(2*atr))+15*clip(1-abs(adjust-.07)/.08)+15*recovery+10*volume+15*risk(m20-2*atr,d.High.tail(10).max())
    if 0<=p-resistance<=2*atr and p>prev and m20>m60 and volume>.2:
        out['breakout']=25*clip((p-resistance)/atr)+20*volume+20*recovery+15*clip((m20/m60-1)/.12)+10*clip(1-(p-resistance)/(2*atr))+10*risk(resistance-atr,p+2*atr)
    stop=min(d.Low.tail(10).min(),p-atr*.5)
    target=resistance
    rr=(target-p)/(p-stop) if stop<p<target else 0
    r=float(rsi.iloc[-1]); risk_pct=(p-stop)/p
    if r>=75 or p<support or (p<m60 and recovery<=0) or risk_pct>.10:
        judgment='매수보류'
    elif p>m20>m60 and 45<=r<=65 and recovery>=.4 and rr>=2 and risk_pct<=.05:
        judgment='적극매수'
    elif 35<=r<=70 and recovery>0 and risk_pct<=.08 and (rr>=1.5 or out.get('breakout',0)>=65):
        judgment='분할매수'
    else:
        judgment='관망'
    return {**{k:round(out.get(k,float('nan')),2) for k in FIELDS},'entry_judgment':judgment}

def rank_pattern(d,mode):
    key=MODES[mode]
    if key not in d: return d.iloc[:0].copy()
    d=d.copy(); v=pd.to_numeric(d[key],errors='coerce')
    d=d.loc[np.isfinite(v)&v.between(0,100)].copy()
    d['추천 참고점수']=v.loc[d.index]; d['ranking_score']=d['추천 참고점수']
    return d.sort_values(['추천 참고점수','ticker'],ascending=[False,True])
