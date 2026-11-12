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
    history.append({'source':'수동 실행' if cron=='manual' else '예약 실행','slot':key,'captured':pd.Timestamp.now(tz='Asia/Seoul').isoformat(),'groups':groups,'outcomes':{},'entry_review':entry_review}); PATH.write_text(json.dumps(history,ensure_ascii=False))

def validate():
    import yfinance as yf
    history=load(); now=pd.Timestamp.now(tz='UTC'); pending={}
    for s in history:
        if (now-pd.Timestamp(s['captured'])).days>60: continue
        for rows in s['groups'].values():
            for r in rows:
                t=r['ticker']; o=s['outcomes'].setdefault(t,{})
                if '20' not in o: pending.setdefault(t,[]).append(s) if s not in pending.get(t,[]) else None
    for t,records in sorted(pending.items(),key=lambda kv:min(s['outcomes'][kv[0]].get('last_attempt','') for s in kv[1]))[:40]:
        for s in records: s['outcomes'][t]['last_attempt']=now.isoformat()
        try:
            first=min(pd.Timestamp(s['captured']) for s in records)
            bars=yf.Ticker(t).history(start=(first-pd.Timedelta(days=2)).date().isoformat(),auto_adjust=True,timeout=10)
            c=bars.Close.dropna(); dates=pd.DatetimeIndex(c.index).tz_localize(None).normalize(); c.index=dates; c=c[~c.index.duplicated()].sort_index()
            # Conservative baseline: first completed session strictly after capture's exchange-local date.
            zone='Asia/Seoul' if t.endswith(('.KS','.KQ')) else 'America/New_York'
            cutoff=now.tz_convert(zone).date()
            c=c[c.index<pd.Timestamp(cutoff)]
            for s in records:
                day=pd.Timestamp(s['captured']).tz_convert(zone).date(); future=c[c.index>pd.Timestamp(day)]
                if future.empty or future.iloc[0]<=0: continue
                o=s['outcomes'][t]; o.setdefault('base_date',str(future.index[0].date())); o.setdefault('base',float(future.iloc[0])); base=pd.Timestamp(o['base_date']); after=c[c.index>base]
                if base not in c.index or abs(c.loc[base]/o['base']-1)>.015: continue
                for h in (1,5,20):
                    if len(after)>=h: o.setdefault(str(h),round(100*(float(after.iloc[h-1])/o['base']-1),2))
        except Exception as e: print(t,type(e).__name__)
    if history: PATH.write_text(json.dumps(history,ensure_ascii=False))

if __name__=='__main__':
    capture(); validate()
