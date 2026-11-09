"""Independent scheduled market scanner. Scores are technical heuristics, not probabilities."""
from __future__ import annotations
import io, json, os, re
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'market_scan_data'
COLS = ['ticker','name','market','asset_type']

def clean_catalog(frame):
    if frame is None or frame.empty: return pd.DataFrame(columns=COLS)
    f=frame.copy()
    for c in COLS:
        if c not in f: f[c]=''
    f=f[COLS].fillna('').astype(str)
    f['ticker']=f.ticker.str.strip().str.upper()
    f=f[f.ticker.str.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,19}')]
    f=f[~f.ticker.str.startswith('^')]
    return f.drop_duplicates('ticker',keep='last').reset_index(drop=True)

def us_listings():
    out=[]
    sources=[('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt','NASDAQ','Security Name','ETF'),('https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt','NYSE/OTHER','Security Name','ETF')]
    for url, market, name_col, etf_col in sources:
        try:
            resp=requests.get(url,timeout=20,headers={'User-Agent':'Mozilla/5.0'}); resp.raise_for_status()
            f=pd.read_csv(io.StringIO(resp.text),sep='|',dtype=str)
            symbol='Symbol' if 'Symbol' in f else 'ACT Symbol'
            if symbol not in f: continue
            f=f[~f[symbol].fillna('').str.contains('File Creation Time',case=False)]
            if 'Test Issue' in f: f=f[f['Test Issue'].eq('N')]
            for _,r in f.iterrows():
                ticker=str(r.get(symbol,'')).replace('$','-').replace('/','-').strip()
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,19}',ticker): continue
                etf=str(r.get(etf_col,'N')).upper()=='Y'
                out.append((ticker,str(r.get(name_col,ticker)),market,'ETF' if etf else 'STOCK'))
        except Exception as exc: print('US LIST WARNING',market,type(exc).__name__,str(exc)[:100])
    return pd.DataFrame(out,columns=COLS)

def kr_listings():
    out=[]
    try:
        from pykrx import stock
        today=datetime.now().strftime('%Y%m%d')
        for market,suffix in [('KOSPI','.KS'),('KOSDAQ','.KQ')]:
            for t in stock.get_market_ticker_list(today,market=market):
                out.append((t+suffix,stock.get_market_ticker_name(t),market,'STOCK'))
        for t in stock.get_etf_ticker_list(today):
            out.append((t+'.KS',stock.get_etf_ticker_name(t),'KR ETF','ETF'))
    except Exception as exc: print('KR LIST WARNING',type(exc).__name__,str(exc)[:150])
    return pd.DataFrame(out,columns=COLS)

def load_catalog():
    DATA.mkdir(exist_ok=True)
    p=DATA/'catalog.csv'
    prior=pd.read_csv(p,dtype=str) if p.exists() else pd.DataFrame(columns=COLS)
    parts=[us_listings(),kr_listings()]
    # preserve previously discovered symbols when a provider is temporarily unavailable
    for part in parts:
        if not part.empty: prior=pd.concat([prior,part],ignore_index=True)
    catalog=clean_catalog(prior)
    if catalog.empty: raise RuntimeError('No catalog available: check market providers or seed catalog.csv')
    catalog.to_csv(p,index=False,encoding='utf-8-sig')
    return catalog

def technical_score(history):
    if history is None or history.empty or 'Close' not in history: return None
    close=pd.to_numeric(history['Close'],errors='coerce').dropna()
    if len(close)<65 or (close<=0).any(): return None
    last=float(close.iloc[-1]); ma20=float(close.tail(20).mean()); ma60=float(close.tail(60).mean())
    ret5=float(last/close.iloc[-6]-1); ret20=float(last/close.iloc[-21]-1)
    daily=close.pct_change().dropna(); vol=float(daily.tail(60).std()*np.sqrt(252))
    if not np.isfinite(vol): return None
    score=float(np.clip(50 + (12 if last>ma20 else -12) + (10 if ma20>ma60 else -10) + np.clip(ret20*100, -15,15) - max(0,vol-.5)*15,0,100))
    return {'close':round(last,4),'score':round(score,2),'return_5d_pct':round(ret5*100,2),'return_20d_pct':round(ret20*100,2),'volatility_annual':round(vol,4),'asof_price':str(close.index[-1].date())}

def scan_one(ticker):
    h=yf.Ticker(ticker).history(period='6mo',interval='1d',timeout=10,auto_adjust=True)
    return technical_score(h)

def run(batch_size=100):
    catalog=load_catalog()
    DATA.mkdir(exist_ok=True)
    results_path=DATA/'scores.csv'; state_path=DATA/'state.json'
    existing=pd.read_csv(results_path,dtype={'ticker':str}) if results_path.exists() else pd.DataFrame()
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    cursor=int(state.get('cursor',0)) % len(catalog)
    n=min(max(1,int(batch_size)),len(catalog))
    chosen=pd.concat([catalog.iloc[cursor:],catalog.iloc[:cursor]],ignore_index=True).head(n)
    from concurrent.futures import ThreadPoolExecutor,as_completed
    records=[]; failures=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(scan_one,r.ticker):r for r in chosen.itertuples(index=False)}
        for future in as_completed(futures):
            r=futures[future]
            try:
                result=future.result()
                if result:
                    records.append({'ticker':r.ticker,'name':r.name,'market':r.market,'asset_type':r.asset_type,**result,'scanned_at_utc':datetime.now(timezone.utc).isoformat()})
                else: failures.append({'ticker':r.ticker,'reason':'insufficient price history'})
            except Exception as exc: failures.append({'ticker':r.ticker,'reason':f'{type(exc).__name__}: {str(exc)[:90]}'})
    if records:
        new=pd.DataFrame(records)
        merged=pd.concat([existing,new],ignore_index=True) if not existing.empty else new
        merged=merged.drop_duplicates('ticker',keep='last')
        # Observe actual later prices for previously scanned symbols. This is NOT a trade backtest.
        if not existing.empty and {'ticker','close','asof_price','scanned_at_utc'}.issubset(existing.columns):
            old=existing.drop_duplicates('ticker',keep='last')[['ticker','close','asof_price','scanned_at_utc']]
            follow=new[['ticker','close','asof_price','scanned_at_utc']].merge(old,on='ticker',suffixes=('_new','_old'))
            follow=follow[pd.to_datetime(follow.asof_price_new,errors='coerce') > pd.to_datetime(follow.asof_price_old,errors='coerce')].copy()
            if not follow.empty:
                follow['observed_return_pct']=((pd.to_numeric(follow.close_new,errors='coerce')/pd.to_numeric(follow.close_old,errors='coerce')-1)*100).round(2)
                follow=follow.replace([np.inf,-np.inf],np.nan).dropna(subset=['observed_return_pct'])
                obs_path=DATA/'observations.csv'
                old_obs=pd.read_csv(obs_path) if obs_path.exists() else pd.DataFrame()
                all_obs=pd.concat([old_obs,follow],ignore_index=True)
                all_obs=all_obs.drop_duplicates(['ticker','asof_price_old','asof_price_new'],keep='last')
                all_obs.to_csv(obs_path,index=False,encoding='utf-8-sig')
        merged.to_csv(results_path,index=False,encoding='utf-8-sig')
    elif not results_path.exists():
        pd.DataFrame(columns=['ticker','name','market','asset_type','close','score','return_5d_pct','return_20d_pct','volatility_annual','asof_price','scanned_at_utc']).to_csv(results_path,index=False,encoding='utf-8-sig')
    state={'cursor':(cursor+n)%len(catalog),'catalog_size':len(catalog),'attempted':n,'succeeded':len(records),'failed':len(failures),'updated_utc':datetime.now(timezone.utc).isoformat()}
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    pd.DataFrame(failures,columns=['ticker','reason']).to_csv(DATA/'last_failures.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(state,ensure_ascii=False))
    return state

if __name__=='__main__': run(int(os.getenv('SCAN_BATCH_SIZE','100')))
