import pandas as pd
from qp_refresh_r23 import resolve_catalog, refresh_candidates, expected_weekday

def test_symbol():
    c=pd.DataFrame({'ticker':['186230.KQ','005930.KS'],'name':['그린플러스','삼성전자']})
    assert resolve_catalog('그린 플러스',c)=='186230.KQ'
    assert resolve_catalog('186230',c)=='186230.KQ'
    assert resolve_catalog('없는 종목',c)==''
    assert resolve_catalog('NVDA',c)=='NVDA'

def test_refresh():
    d=pd.DataFrame({'ticker':['A','B'],'score':[1,2]})
    def fetch(t):
        if t=='B': raise RuntimeError()
        return dict(score=80,close=10,return_5d_pct=1,return_20d_pct=2,volatility_annual=.2,asof_price='2026-11-17')
    out,failed=refresh_candidates(d,fetch,now=pd.Timestamp('2026-11-17 22:00Z'))
    assert list(out.ticker)==['A'] and failed==['B'] and out.iloc[0].score==80
    assert d.iloc[0].score==1

def test_weekday():
    assert str(expected_weekday(pd.Timestamp('2026-11-16 00:00Z'),True))=='2026-11-16'
    assert str(expected_weekday(pd.Timestamp('2026-11-16 00:00Z'),False))=='2026-11-13'
