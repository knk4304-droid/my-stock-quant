import pandas as pd
from qp_index_live import index_quote
from qp_rank_r26 import rank, challenger_components

def test_intraday_and_completed():
    daily=pd.DataFrame({'Close':[100,110]},index=pd.DatetimeIndex(['2026-11-20','2026-11-23'],tz='Asia/Seoul'))
    intra=pd.DataFrame({'Close':[115]},index=pd.DatetimeIndex(['2026-11-24 13:00'],tz='Asia/Seoul'))
    def fetch(**kw): return intra if kw['interval']=='5m' else daily
    p,c,t,s=index_quote('^KS11',fetch,pd.Timestamp('2026-11-24 04:05Z'))
    assert p==115 and abs(c-100*(115/110-1))<1e-8 and '장중' in s
    p,c,t,s=index_quote('^KS11',fetch,pd.Timestamp('2026-11-24 00:00Z')-pd.Timedelta(minutes=1))
    assert p==110 and t=='2026-11-23'

def test_same_sample_and_components():
    d=pd.DataFrame([dict(ticker='A',score=80,return_5d_pct=12,return_20d_pct=8,volatility_annual=.3),dict(ticker='B',score=60,return_5d_pct=-9,return_20d_pct=2,volatility_annual=.4)])
    for period in ['단기','스윙','중기','장기']:
        a=rank(d,period); b=rank(d,period,challenger=True)
        assert set(a.ticker)==set(b.ticker)
        for _,r in b.iterrows(): assert abs(sum(challenger_components(r,period).values())-r['추천 참고점수'])<=.051
