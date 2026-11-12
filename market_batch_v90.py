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

# Minimal verified Korean-listed ETF seed universe. The scheduled scanner
# expands this list when pykrx becomes available; seeds are not scan results.
KR_ETF_SEEDS = [
    ('069500.KS', 'KODEX 200', 'KR ETF', 'ETF'),
    ('102110.KS', 'TIGER 200', 'KR ETF', 'ETF'),
    ('360750.KS', 'TIGER 미국S&P500', 'KR ETF', 'ETF'),
    ('133690.KS', 'TIGER 미국나스닥100', 'KR ETF', 'ETF'),
]

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
    """Collect Korean listings with an independent fallback; never label unknown markets as KOSPI."""
    out=[]
    try:
        from pykrx import stock
        # A market holiday/weekend can return no rows for the current day.
        from datetime import timedelta
        for offset in range(0, 8):
            day=(datetime.now()-timedelta(days=offset)).strftime('%Y%m%d')
            found=[]
            for market,suffix in [('KOSPI','.KS'),('KOSDAQ','.KQ')]:
                for t in stock.get_market_ticker_list(day,market=market):
                    found.append((t+suffix,stock.get_market_ticker_name(t),market,'STOCK'))
            for t in stock.get_etf_ticker_list(day):
                found.append((t+'.KS',stock.get_etf_ticker_name(t),'KR ETF','ETF'))
            if found:
                out.extend(found)
                break
    except Exception as exc:
        print('KR PYKRX WARNING',type(exc).__name__,str(exc)[:150])
    if not out:
        try:
            import FinanceDataReader as fdr
            f=fdr.StockListing('KRX')
            for _,r in f.iterrows():
                code=str(r.get('Code',r.get('Symbol',''))).strip().zfill(6)
                market=str(r.get('Market','')).upper()
                if not re.fullmatch(r'\d{6}',code) or market not in ('KOSPI','KOSDAQ','KONEX'): continue
                if market=='KONEX': continue  # Yahoo suffix not reliably supported
                out.append((code+('.KQ' if market=='KOSDAQ' else '.KS'),str(r.get('Name',code)),market,'STOCK'))
        except Exception as exc:
            print('KR FDR WARNING',type(exc).__name__,str(exc)[:150])
    if not out:
        print('KR LIST WARNING: no Korean stocks obtained; using Korean ETF seed candidates')
    # Keep ETF coverage even when pykrx/FDR fails or returns only equities.
    out.extend(KR_ETF_SEEDS)
    return clean_catalog(pd.DataFrame(out,columns=COLS))


def choose_balanced_batch(catalog, state, batch_size):
    """Allocate each run across available markets rather than exhausting NASDAQ first."""
    markets=sorted(catalog.market.dropna().unique().tolist())
    if not markets: return catalog.head(0), {}
    cursors=state.get('market_cursors',{})
    n=min(max(1,int(batch_size)),len(catalog))
    quotas={m:n//len(markets) for m in markets}
    for m in markets[:n%len(markets)]: quotas[m]+=1
    chosen=[]; next_cursors={}
    for m in markets:
        subset=catalog[catalog.market.eq(m)].reset_index(drop=True)
        cursor=int(cursors.get(m,0))%len(subset)
        count=min(quotas[m],len(subset))
        indices=[(cursor+i)%len(subset) for i in range(count)]
        chosen.append(subset.iloc[indices])
        next_cursors[m]=(cursor+count)%len(subset)
    result=pd.concat(chosen,ignore_index=True)
    # Fill spare quota when one market contains fewer symbols than its allocation.
    if len(result)<n:
        missing=catalog[~catalog.ticker.isin(result.ticker)].head(n-len(result))
        result=pd.concat([result,missing],ignore_index=True)
    return result, next_cursors

def load_catalog():
    DATA.mkdir(exist_ok=True)
    p=DATA/'catalog.csv'
    prior=pd.read_csv(p,dtype=str) if p.exists() else pd.DataFrame(columns=COLS)
    parts=[us_listings(),kr_listings()]
    # preserve previously discovered symbols when a provider is temporarily unavailable
    for part in parts:
        if not part.empty: prior=pd.concat([prior,part],ignore_index=True)
    # Seeds also recover older catalogs created before Korean ETF support.
    prior=pd.concat([prior,pd.DataFrame(KR_ETF_SEEDS,columns=COLS)],ignore_index=True)
    from qp_universe_r18 import eligible
    catalog=eligible(clean_catalog(prior))
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

def run(batch_size=250):
    catalog=load_catalog()
    DATA.mkdir(exist_ok=True)
    results_path=DATA/'scores.csv'; state_path=DATA/'state.json'
    existing=pd.read_csv(results_path,dtype={'ticker':str}) if results_path.exists() else pd.DataFrame()
    from qp_universe_r18 import eligible
    if not existing.empty:
        excluded=existing.loc[~existing.ticker.isin(eligible(existing).ticker)]
        if not excluded.empty:
            archive=DATA/'excluded_etp_history.csv'
            prev=pd.read_csv(archive,dtype={'ticker':str}) if archive.exists() else pd.DataFrame()
            pd.concat([prev,excluded],ignore_index=True).drop_duplicates('ticker',keep='last').to_csv(archive,index=False,encoding='utf-8-sig')
        existing=eligible(existing)
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    from qp_universe_r18 import choose, eligible
    # Retain past scores for audit, but never revisit or recommend excluded ETPs.
    chosen, next_cursors, selection_counts=choose(catalog,existing,state,batch_size,choose_balanced_batch,
                                                  revisit_limit=int(os.getenv('REVISIT_TOP_N','25')))
    print('R18 selection groups',selection_counts)
    print('KR ETF CATALOG',int(catalog.market.eq('KR ETF').sum()),
          'KR ETF BATCH',int(chosen.market.eq('KR ETF').sum()))
    next_cursors={**state.get('market_cursors',{}),**next_cursors}
    n=int(selection_counts.get('신규 순환 발굴',0))
    attempted_total=len(chosen)
    from concurrent.futures import ThreadPoolExecutor,as_completed
    records=[]; failures=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
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
    state={'market_cursors':next_cursors,'catalog_by_market':{str(k):int(v) for k,v in catalog.market.value_counts().items()},'scanned_by_market':{str(k):int(v) for k,v in new.market.value_counts().items()} if records else {},'catalog_size':len(catalog),'attempted':attempted_total,'rotation_count':n,'revisit_count':int(selection_counts.get('기존 우수 후보',0)),'selection_groups':selection_counts,'succeeded':len(records),'failed':len(failures),'updated_utc':datetime.now(timezone.utc).isoformat()}
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    pd.DataFrame(failures,columns=['ticker','reason']).to_csv(DATA/'last_failures.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(state,ensure_ascii=False))
    return state

if __name__=='__main__': run(int(os.getenv('SCAN_BATCH_SIZE','250')))
