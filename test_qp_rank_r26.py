import pandas as pd
from qp_rank_r26 import rank
from qp_discovery_r25 import candidate_pool

def sample():
 return pd.DataFrame(dict(ticker=['B','A','C','D'],score=[80,80,95,None],return_5d_pct=[2,2,25,1],return_20d_pct=[5,5,40,1],volatility_annual=[.2,.2,.3,.2]))
def test_deterministic_and_missing():
 d=rank(sample(),'스윙'); assert list(d.ticker)==['C','A','B']; assert list(rank(sample().iloc[::-1],'스윙').ticker)==list(d.ticker)
def test_entry():
 assert list(rank(sample(),'스윙',entry=True).ticker)==['A','B','C']
def test_challenger():
 d=rank(sample(),'스윙',challenger=True); assert d.iloc[0].ticker=='A'
def test_full_discovery():
 d=pd.DataFrame(dict(ticker=[str(i) for i in range(500)],return_5d_pct=range(500),return_20d_pct=0,scanned_at_utc='2026-11-17')); assert '499' in set(candidate_pool(d).ticker)
