"""R20 opt-in live refresh. Price data may be delayed: never label it exchange realtime."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np
from qp_universe_r18 import eligible
def technical_score(history):
    close=pd.to_numeric(history['Close'],errors='coerce').dropna()
    if len(close)<65 or (close<=0).any():return None
    last=float(close.iloc[-1]); ma20=float(close.tail(20).mean()); ma60=float(close.tail(60).mean())
    ret5=float(last/close.iloc[-6]-1);ret20=float(last/close.iloc[-21]-1)
    vol=float(close.pct_change().tail(60).std()*np.sqrt(252))
    if not np.isfinite(vol):return None
    score=float(np.clip(50+(12 if last>ma20 else -12)+(10 if ma20>ma60 else -10)+np.clip(ret20*100,-15,15)-max(0,vol-.5)*15,0,100))
    return {'close':round(last,4),'score':round(score,2),'return_5d_pct':round(ret5*100,2),'return_20d_pct':round(ret20*100,2),'volatility_annual':round(vol,4),'asof_price':str(close.index[-1].date())}


DATA=Path(__file__).resolve().parent/'market_scan_data'

def market_of(t):
    return 'KR' if str(t).endswith(('.KS','.KQ')) else 'US'

def select_candidates(catalog, scores, cap=500, strategy='혼합형'):
    """Deterministic selection: 250 KR / 250 US, 5 disjoint buckets per market.
    Scores are historical scanner heuristics, not verified fundamentals or fresh quotes.
    """
    cat=eligible(catalog).drop_duplicates('ticker').copy()
    if cat.empty: return cat.assign(selection_group=pd.Series(dtype=str))
    cat['region']=cat.ticker.map(market_of)
    s=scores.copy() if scores is not None else pd.DataFrame()
    if not s.empty and {'ticker','score'}.issubset(s.columns):
        s=s.drop_duplicates('ticker',keep='last')[[k for k in ('ticker','score','return_20d_pct','scanned_at_utc') if k in s.columns]]
        cat=cat.merge(s,on='ticker',how='left')
    for k in ('score','return_20d_pct'):
        if k not in cat: cat[k]=np.nan
        cat[k]=pd.to_numeric(cat[k],errors='coerce')
    if 'scanned_at_utc' not in cat: cat['scanned_at_utc']=''
    cat['scanned_at_utc']=pd.to_datetime(cat.scanned_at_utc,utc=True,errors='coerce')
    # Stable hash-like rotation: day changes membership, no random dependence.
    day=int(datetime.now(timezone.utc).strftime('%Y%m%d'))
    cat['rotation']=cat.ticker.map(lambda t:(sum((i+1)*ord(c) for i,c in enumerate(t)) * 131 + day*97) % 100003)
    chosen=[]; seen=set()
    for region in ('KR','US'):
        part=cat[cat.region.eq(region)].copy()
        n=min(len(part),cap//2 + (cap%2 if region=='KR' else 0))
        if not n: continue
        if strategy=='점수 우선': quotas=[('저장점수',n)]
        elif strategy=='순환 우선': quotas=[('순환 발굴',n)]
        else:
            quotas=[('대표·유동성 관찰',n//5),('성장·모멘텀 관찰',n//5),('테마 추세 관찰',n//5),('과거 우수 재검토',n//10),('신규·순환 발굴',n-3*(n//5)-n//10)]
        for group,limit in quotas:
            if group=='대표·유동성 관찰':
                # No verified liquidity feed: prioritize known R18 anchor symbols, never claim real market cap.
                from qp_universe_r18 import QUALITY
                order={t:i for i,t in enumerate(QUALITY)}
                p=part.assign(_rank=part.ticker.map(lambda t:order.get(t,100000))) .sort_values(['_rank','score'],ascending=[True,False],na_position='last')
            elif group=='성장·모멘텀 관찰': p=part.sort_values(['return_20d_pct','score'],ascending=False,na_position='last')
            elif group=='테마 추세 관찰':
                from qp_universe_r18 import THEME
                order={t:i for i,t in enumerate(THEME)}
                p=part.assign(_rank=part.ticker.map(lambda t:order.get(t,100000))).sort_values(['_rank','score'],ascending=[True,False],na_position='last')
            elif group in ('과거 우수 재검토','저장점수'): p=part.sort_values(['score','scanned_at_utc'],ascending=False,na_position='last')
            else: p=part.sort_values(['rotation','ticker'])
            added=0
            for _,row in p.iterrows():
                if row.ticker in seen: continue
                d=row.to_dict();d['selection_group']=group;chosen.append(d);seen.add(row.ticker);added+=1
                if added>=limit:break
        if sum(x['region']==region for x in chosen)<n:
            for _,row in part.sort_values('rotation').iterrows():
                if row.ticker in seen:continue
                d=row.to_dict();d['selection_group']='부족분 보충';chosen.append(d);seen.add(row.ticker)
                if sum(x['region']==region for x in chosen)>=n:break
    return pd.DataFrame(chosen).drop(columns=['_rank'],errors='ignore')

def fresh_check(bars, ticker, now=None):
    """Validate completed daily bar age by exchange-local business days; never call intraday realtime."""
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:now=now.tz_localize('UTC')
    zone='Asia/Seoul' if market_of(ticker)=='KR' else 'America/New_York'
    local=now.tz_convert(zone)
    d=bars.dropna(subset=['Close']).sort_index()
    if len(d)<65: return None,'일봉 부족'
    last=pd.Timestamp(d.index[-1]); last=last.tz_localize(zone) if last.tzinfo is None else last.tz_convert(zone)
    if last.date()>local.date():return None,'미래 기준일'
    # business-day age; holidays may require a separate exchange calendar
    age=np.busday_count(last.date(),local.date())
    if age>2:return None,f'가격 자료 지연: {age}영업일'
    out=technical_score(d)
    if out is None:return None,'기술지표 계산 불가'
    out['age_business_days']=int(age)
    out['price_basis']='일봉 기준 · 실시간 체결가 아님'
    return out,None

def fetch_and_score(selected, max_workers=5, fetcher=None, now=None):
    if fetcher is None:
        import yfinance as yf
        def fetcher(t):return yf.Ticker(t).history(period='9mo',interval='1d',auto_adjust=True,timeout=10)
    rows=[];failed=[]
    with ThreadPoolExecutor(max_workers=min(5,max(1,max_workers))) as pool:
        jobs={pool.submit(fetcher,t):t for t in selected.ticker.astype(str)}
        for future in as_completed(jobs):
            t=jobs[future]
            try:
                metrics,err=fresh_check(future.result(),t,now)
                if err:failed.append({'ticker':t,'reason':err});continue
                rows.append({'ticker':t,**metrics})
            except Exception as exc:failed.append({'ticker':t,'reason':f'{type(exc).__name__}: {str(exc)[:100]}'})
    return pd.DataFrame(rows),pd.DataFrame(failed)

def rank_current(selected, fresh, top_n=50):
    if fresh.empty:return pd.DataFrame()
    m=selected[['ticker','name','market','region','selection_group']].merge(fresh,on='ticker',how='inner')
    # Current price-derived score; previous historical score is NOT used for final ranking.
    m=m.sort_values(['score','return_20d_pct'],ascending=False)
    return m.head(top_n).reset_index(drop=True)

def simulate_strategies():
    """Deterministic synthetic scenario coverage, not realized market returns/backtest."""
    import random
    rng=random.Random(20261113)
    scenarios=['상승장','횡보장','급락장','테마 순환장']
    result=[]
    for scenario in scenarios:
        # Each strategy gets the same synthetic universe; assess hit coverage and concentration.
        universe=[]
        for i in range(1000):
            momentum=rng.uniform(-1,1);quality=rng.uniform(0,1);new=rng.random()<.22
            if scenario=='상승장':signal=.55*momentum+.35*quality+.1*rng.random()
            elif scenario=='횡보장':signal=.15*momentum+.7*quality+.15*rng.random()
            elif scenario=='급락장':signal=-.5*momentum+.45*quality+.05*rng.random()
            else:signal=.4*momentum+.15*quality+(.45 if new else 0)
            universe.append((i,signal,quality,momentum,new))
        winners={r[0] for r in sorted(universe,key=lambda r:r[1],reverse=True)[:100]}
        for strategy in ['점수 우선','순환 우선','혼합형']:
            if strategy=='점수 우선': chosen=sorted(universe,key=lambda r:r[2],reverse=True)[:500]
            elif strategy=='순환 우선': chosen=sorted(universe,key=lambda r:(r[0]*271)%1009)[:500]
            else:
                a=sorted(universe,key=lambda r:r[2],reverse=True)[:250]
                b=sorted(universe,key=lambda r:r[3],reverse=True)
                c=sorted(universe,key=lambda r:(r[0]*271)%1009)
                seen={r[0] for r in a}
                for r in b[:200]+c:
                    if len(a)>=500:break
                    if r[0] not in seen:a.append(r);seen.add(r[0])
                chosen=a
            coverage=len(winners&{r[0] for r in chosen})
            result.append({'시장 시나리오':scenario,'방식':strategy,'상위 100개 포착':coverage,'포착률(%)':coverage})
    return pd.DataFrame(result)

def show(st):
    st.subheader('🔄 현재 시점 종합 재조회 · R20')
    st.caption('저장된 전체 시장 목록에서 최대 500개를 선별하고, 버튼을 누를 때만 일봉 가격을 재조회합니다. 실시간 체결가/호가가 아니며 뉴스·공시 자동 검증은 아직 포함되지 않습니다.')
    catalog_path=DATA/'catalog.csv'; scores_path=DATA/'scores.csv'
    if not catalog_path.exists():st.warning('자동분석 종목 목록(catalog.csv)이 없습니다.');return
    catalog=pd.read_csv(catalog_path,dtype=str)
    scores=pd.read_csv(scores_path,dtype={'ticker':str}) if scores_path.exists() else pd.DataFrame()
    strategy=st.selectbox('후보 선정 방식',['혼합형','점수 우선','순환 우선'],key='r20_strategy')
    limit=st.select_slider('이번 조회 최대 종목 수',[20,50,100,200,300,500],value=100,key='r20_limit')
    selected=select_candidates(catalog,scores,cap=limit,strategy=strategy)
    st.caption(f'선정 {len(selected)}개 · 국내 {sum(selected.region.eq("KR"))}개 / 미국 {sum(selected.region.eq("US"))}개 · 자동으로 조회하지 않음')
    with st.expander('선정 후보 및 시뮬레이션 비교'):
        st.dataframe(selected[['ticker','name','region','selection_group']].head(100),hide_index=True,use_container_width=True)
        sim=simulate_strategies();st.dataframe(sim,hide_index=True,use_container_width=True)
        st.caption('시뮬레이션은 합성 점수 기반 포착률 비교입니다. 실제 과거 수익률 백테스트가 아니며 우수 전략의 실증 증거가 아닙니다.')
    if st.button('선택 종목 최신 일봉 재조회',key='r20_run',type='primary'):
        with st.spinner(f'{len(selected)}개 종목 가격 조회 중 · 공급원 요청 제한으로 시간이 걸릴 수 있습니다'):
            fresh,failed=fetch_and_score(selected)
        st.session_state['r20_result']=(selected,fresh,failed,datetime.now(timezone.utc).isoformat())
    if 'r20_result' not in st.session_state:return
    old, fresh, failed, ts=st.session_state['r20_result']
    st.caption(f'실행 시각(UTC): {ts} · 요청 {len(old)} · 성공 {len(fresh)} · 실패/지연 {len(failed)}')
    if fresh.empty:st.error('유효한 가격 자료가 없어 추천을 생성하지 않았습니다.');return
    ranked=rank_current(old,fresh)
    st.dataframe(ranked[['ticker','name','region','selection_group','close','asof_price','score','return_20d_pct','price_basis']].head(10),hide_index=True,use_container_width=True)
    st.caption('위 TOP10은 기술적 관찰 후보이며 매수 추천/주문 신호가 아닙니다. 뉴스·공시·실시간 호가·손익비 검증 전에는 매수 판단을 확정하지 않습니다.')
    if not failed.empty:
        with st.expander(f'조회 실패 및 자료 지연 {len(failed)}개'):
            st.dataframe(failed,hide_index=True,use_container_width=True)
    st.download_button('이번 조회 결과 CSV',ranked.to_csv(index=False).encode('utf-8-sig'),file_name='quantpilot_r20_observation.csv',mime='text/csv',key='r20_csv')
