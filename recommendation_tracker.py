"""Track historical recommendation snapshots using subsequent scan observations.
No future data is used when a recommendation is created. Observations are not backtests.
"""
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'market_scan_data'
PERIODS = {'단기 (1~3일)': (0.5, 0.8, 0, 12), '스윙 (1~2주)': (0.6, .35, .25, 10),
           '중기 (1~3개월)': (.7, 0, .35, 10), '장기 (1년 이상)': (.8, 0, .15, 18)}
COLS = ['recorded_at_utc','period','ticker','name','market','entry_date','entry_close','rank','score',
        'observed_date','observed_close','elapsed_days','observed_return_pct']


def score_candidates(data, period):
    d=data.copy()
    for k in ['score','return_5d_pct','return_20d_pct','volatility_annual']:
        d[k]=pd.to_numeric(d[k],errors='coerce')
    base=d.score.fillna(0)
    r5=d.return_5d_pct.clip(-25,25).fillna(0)
    r20=d.return_20d_pct.clip(-40,40).fillna(0)
    vol=d.volatility_annual.clip(0,3).fillna(1)
    a,b,c,v=PERIODS[period]
    d['rank_score']=base*a+r5*b+r20*c-vol*v
    return d.sort_values('rank_score',ascending=False)


def update():
    scores_path=DATA/'scores.csv'
    if not scores_path.exists(): return 'scores.csv missing'
    df=pd.read_csv(scores_path,dtype={'ticker':str})
    required={'ticker','name','market','close','asof_price','scanned_at_utc','score','return_5d_pct','return_20d_pct','volatility_annual'}
    if not required.issubset(df.columns): return 'scores.csv columns missing'
    df['scanned_at_utc']=pd.to_datetime(df.scanned_at_utc,utc=True,errors='coerce')
    df['asof_price']=pd.to_datetime(df.asof_price,errors='coerce')
    df['close']=pd.to_numeric(df.close,errors='coerce')
    df=df.dropna(subset=['ticker','asof_price','close','scanned_at_utc'])
    df=df[df.close.gt(0)]
    if df.empty: return 'No valid scan data'
    newest=df.sort_values('scanned_at_utc').drop_duplicates('ticker',keep='last')
    recent=newest[newest.scanned_at_utc.ge(pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=7))]
    path=DATA/'recommendation_history.csv'
    history=pd.read_csv(path,dtype={'ticker':str}) if path.exists() else pd.DataFrame(columns=COLS)
    for k in COLS:
        if k not in history: history[k]=pd.NA
    # Historical snapshots are immutable; later data only fills observed columns.
    if not history.empty:
        for idx,r in history.iterrows():
            ticker=r['ticker']
            if pd.isna(ticker): continue
            entry_date=pd.to_datetime(r['entry_date'],errors='coerce')
            entry_close=pd.to_numeric(r['entry_close'],errors='coerce')
            if pd.isna(entry_date) or pd.isna(entry_close) or entry_close<=0: continue
            later=df[(df.ticker.eq(ticker)) & (df.asof_price.gt(entry_date))].sort_values('asof_price')
            if later.empty: continue
            last=later.iloc[-1]
            # Do not regress a previously observed price to an older date.
            prev=pd.to_datetime(r['observed_date'],errors='coerce')
            if pd.notna(prev) and last.asof_price<=prev: continue
            history.at[idx,'observed_date']=last.asof_price.date().isoformat()
            history.at[idx,'observed_close']=last.close
            history.at[idx,'elapsed_days']=int((last.asof_price-entry_date).days)
            history.at[idx,'observed_return_pct']=round((last.close/entry_close-1)*100,2)
    today=datetime.now(timezone.utc).date().isoformat()
    new=[]
    if not recent.empty:
        for period in PERIODS:
            for rank,(_,r) in enumerate(score_candidates(recent,period).head(10).iterrows(),1):
                key=(history['recorded_at_utc'].astype(str).str[:10].eq(today) &
                     history['period'].eq(period) & history['ticker'].eq(r.ticker))
                if key.any(): continue
                new.append({'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'period':period,
                            'ticker':r.ticker,'name':r['name'],'market':r.market,
                            'entry_date':r.asof_price.date().isoformat(),'entry_close':r.close,
                            'rank':rank,'score':round(float(r.rank_score),2),
                            'observed_date':pd.NA,'observed_close':pd.NA,
                            'elapsed_days':pd.NA,'observed_return_pct':pd.NA})
    if new: history=pd.concat([history,pd.DataFrame(new)],ignore_index=True)
    DATA.mkdir(parents=True,exist_ok=True)
    history.to_csv(path,index=False,encoding='utf-8-sig')
    return f'Existing/created tracked recommendations: {len(history)}; new: {len(new)}'

if __name__=='__main__': print(update())
