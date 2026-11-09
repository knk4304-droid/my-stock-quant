import pandas as pd
from market_batch_v90 import clean_catalog, technical_score
from market_dashboard_v90 import read_snapshot

def test_catalog():
    d=pd.DataFrame([['AAPL','Apple','NASDAQ','STOCK'],['AAPL','Apple2','NASDAQ','STOCK'],['bad ticker','x','x','x']],columns=['ticker','name','market','asset_type'])
    out=clean_catalog(d)
    assert len(out)==1 and out.iloc[0]['name']=='Apple2'

def test_scoring():
    d=pd.DataFrame({'Close':[100+i*.1 for i in range(90)]},index=pd.date_range('2026-01-01',periods=90))
    r=technical_score(d)
    assert r and 0<=r['score']<=100
    assert technical_score(d.head(30)) is None

def test_no_data():
    state,df=read_snapshot()
    assert isinstance(state,dict) and isinstance(df,pd.DataFrame)
