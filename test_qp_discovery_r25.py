import pandas as pd
from qp_discovery_r25 import candidate_pool, valid_prices
from qp_universe_r18 import choose

def test_pool():
 d=pd.DataFrame({'ticker':[f'T{i}' for i in range(100)],'return_5d_pct':range(100),'return_20d_pct':0,'scanned_at_utc':'2026-11-17'})
 p=candidate_pool(d); assert len(p)==60 and p.ticker.is_unique and set(d.ticker[:20])<=set(p.ticker) and 'T99' in set(p.ticker)

def test_prices():
 d=pd.DataFrame(dict(ticker=['A','B','C'],score=[80,80,80],close=[10,10,10],return_5d_pct=[1,1,None],return_20d_pct=2,volatility_annual=.2,asof_price=['2026-11-17','2026-11-10','2026-11-17']))
 assert list(valid_prices(d,pd.Timestamp('2026-11-18T00:00Z')).ticker)==['A']

def test_rotation():
 d=pd.DataFrame(dict(ticker=[f'T{i}' for i in range(100)],name='test',market='NASDAQ',asset_type='STOCK'))
 a,c,_=choose(d,pd.DataFrame(),{},20,None); b,e,_=choose(d,pd.DataFrame(),{'market_cursors':c},20,None)
 assert not set(a.ticker)&set(b.ticker) and c['NASDAQ']==20 and e['NASDAQ']==40
