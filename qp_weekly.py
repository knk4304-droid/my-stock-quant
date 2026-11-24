"""Scheduled snapshots and forward close-to-close evaluation, independent of legacy records."""
import json, os
from pathlib import Path
import pandas as pd
from ranking_history import ranking, PERIODS
DATA=Path(__file__).resolve().parent/'market_scan_data'
PATH=DATA/'qp_weekly_slots.json'

def load():
    return json.loads(PATH.read_text()) if PATH.exists() else []

def slots(week):
    return [pd.Timestamp(week,tz='Asia/Seoul')+pd.Timedelta(days=d,hours=h) for d in range(5) for h in (10,15)]

def week_start(now):
    t=pd.Timestamp(now).tz_convert('Asia/Seoul').normalize(); return (t-pd.Timedelta(days=t.weekday())).date().isoformat()

def capture():
    cron=os.getenv('QP_SCHEDULE',''); now=pd.Timestamp.now(tz='Asia/Seoul')
    if cron not in ('0 1 * * 1-5','0 6 * * 1-5','manual'):
        print('No recognized capture trigger; validation only'); return
    slot=(now.floor('min') if cron=='manual' else now.normalize()+pd.Timedelta(hours=10 if cron.startswith('0 1 ') else 15))
    if cron!='manual' and (now.weekday()>4 or not 0 <= (now-slot).total_seconds() <= 7200):
        print('Scheduled capture skipped: outside 2-hour window'); return
    history=load(); key=slot.isoformat()
    if any(s['slot']==key for s in history): return
    df=pd.read_csv(DATA/'scores.csv',dtype={'ticker':str}); times=pd.to_datetime(df.scanned_at_utc,utc=True,errors='coerce'); df=df.loc[(now-times).dt.total_seconds().between(0,604800)].copy(); df['_time']=times.loc[df.index]; df=df.sort_values('_time').drop_duplicates('ticker',keep='last')
    from qp_discovery_r25 import valid_prices
    df=valid_prices(df,now)
    if df.empty: return
    from qp_home_r12 import current_top
    groups={}
    for p in PERIODS:
        for m in ('전체','한국 주식','미국 주식','국내 ETF','미국 ETF'):
            for theme in ('전체','반도체','AI·기술','금융','헬스케어','배당'):
                top=current_top(df,p,m,theme,ranking)
                groups['|'.join((p,m,theme))]=[{'ticker':str(r.ticker),'name':str(r['name']),'rank':i,'market':str(r.market),'price':float(r.close) if pd.notna(r.close) and float(r.close)>0 else None,'price_date':str(r.get('asof_price',''))} for i,(_,r) in enumerate(top.iterrows(),1)]
    from qp_entry_r16 import capture as capture_entry
    entry_review=capture_entry(groups,now)
    history.append({'source':'수동 실행' if cron=='manual' else '예약 실행','slot':key,'captured':pd.Timestamp.now(tz='Asia/Seoul').isoformat(),'groups':groups,'model_version':'R26-baseline','outcomes':{},'entry_review':entry_review}); PATH.write_text(json.dumps(history,ensure_ascii=False))

def apply_outcome(s,t,bars,now):
    import math
    o=s['outcomes'][t]
    zone='Asia/Seoul' if t.endswith(('.KS','.KQ')) else 'America/New_York'
    local=now.tz_convert(zone)
    c=pd.to_numeric(bars['Close'],errors='coerce').dropna()
    c=c[c.map(lambda v: math.isfinite(v) and v>0)]
    c.index=pd.DatetimeIndex(c.index).tz_localize(None).normalize()
    c=c[~c.index.duplicated(keep='last')].sort_index()
    # Conservative buffer after regular close; exclude current session before then.
    cutoff=pd.Timestamp(local.date())
    if local.hour >= (17 if zone=='Asia/Seoul' else 18): cutoff+=pd.Timedelta(days=1)
    c=c[c.index<cutoff]
    day=pd.Timestamp(s['captured']).tz_convert(zone).date()
    future=c[c.index>pd.Timestamp(day)]
    if future.empty:
        o['status']='기준 거래일 대기 또는 시세 미확보'; return
    if 'base_date' not in o and 'base' not in o:
        o['base_date']=str(future.index[0].date()); o['base']=float(future.iloc[0])
    elif 'base_date' not in o or 'base' not in o:
        o['status']='기준가 기록 불완전 · 재확인 필요'; return
    base=pd.Timestamp(o['base_date'])
    if base not in c.index or abs(c.loc[base]/o['base']-1)>.015:
        o['status']='기준가 불일치 · 재확인 필요'; return
    after=c[c.index>base]
    for h in (1,5,20):
        if len(after)>=h: o.setdefault(str(h),round(100*(float(after.iloc[h-1])/o['base']-1),2))
    o['status']='20일 검증 완료' if '20' in o else f'기준가 확보 · {len(after)}거래일 관측'


def validate(max_tickers=None):
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor
    history=load(); now=pd.Timestamp.now(tz='UTC'); pending={}
    for s in history:
        for t in {r['ticker'] for rows in s['groups'].values() for r in rows}:
            o=s['outcomes'].setdefault(t,{})
            if '20' not in o: pending.setdefault(t,[]).append(s)
    cap=int(max_tickers or os.getenv('QP_VALIDATION_MAX_TICKERS','240'))
    selected=sorted(pending.items(),key=lambda kv:min(s['outcomes'][kv[0]].get('last_attempt','') for s in kv[1]))[:cap]
    def fetch(item):
        t,records=item
        try:
            first=min(pd.Timestamp(s['captured']) for s in records)
            bars=yf.Ticker(t).history(start=(first-pd.Timedelta(days=2)).date().isoformat(),auto_adjust=True,timeout=10,raise_errors=True)
            if bars.empty: raise ValueError('empty history')
            return t,bars,None
        except Exception as e: return t,None,type(e).__name__+': '+str(e)[:150]
    attempted=0
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i in range(0,len(selected),4):
            limited=False
            for t,bars,error in pool.map(fetch,selected[i:i+4]):
                attempted+=1
                if error and any(k in error.lower() for k in ('ratelimit','too many requests','429')):
                    limited=True
                for s in pending[t]:
                    o=s['outcomes'][t]; o['last_attempt']=now.isoformat()
                    try:
                        if error: raise ValueError(error)
                        apply_outcome(s,t,bars,now)
                        o.pop('last_error',None)
                    except Exception as e:
                        o['status']='시세 조회 실패 · 재시도 예정'
                        o['last_error']=str(e)[:180]
                        print(t,type(e).__name__,str(e)[:180])
            if limited:
                print('Validation rate limit: remaining tickers deferred')
                break
    if history:
        tmp=PATH.with_suffix('.tmp'); tmp.write_text(json.dumps(history,ensure_ascii=False)); tmp.replace(PATH)
    print(f'Weekly validation: {attempted}/{len(pending)} tickers')

if __name__=='__main__':
    import sys
    if '--validate-only' not in sys.argv: capture()
    validate()
