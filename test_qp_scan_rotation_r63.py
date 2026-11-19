import pandas as pd
from qp_scan_rotation_r63 import choose

def test_oldest_and_unscanned_first():
    c=pd.DataFrame([{'ticker':t,'name':t,'market':'NASDAQ','asset_type':'STOCK'} for t in ['AAA','BBB','CCC']])
    e=pd.DataFrame([{'ticker':'AAA','scanned_at_utc':'2026-11-19T00:00:00Z'},{'ticker':'BBB','scanned_at_utc':'2026-11-01T00:00:00Z'}])
    result,_,_=choose(c,e,{},2)
    assert result.ticker.tolist()==['CCC','BBB']

def test_market_balance():
    c=pd.DataFrame([{'ticker':f'{m}{i}','name':f'{m}{i}','market':m,'asset_type':'STOCK'} for m in ['NASDAQ','KOSPI'] for i in range(4)])
    result,_,_=choose(c,pd.DataFrame(),{},4)
    assert result.market.value_counts().to_dict()=={'NASDAQ':2,'KOSPI':2}
