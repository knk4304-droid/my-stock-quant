import unittest
import pandas as pd
import numpy as np
from datetime import datetime,timezone
from qp_live_r20 import select_candidates,fresh_check,rank_current,simulate_strategies

class LiveR20Tests(unittest.TestCase):
    def setUp(self):
        self.cat=pd.DataFrame([{'ticker':f'{i:06d}.KS','name':f'KR{i}','market':'KOSPI','asset_type':'STOCK'} for i in range(350)]+[{'ticker':f'US{i}','name':f'US{i}','market':'NASDAQ','asset_type':'STOCK'} for i in range(350)])
        self.scores=pd.DataFrame({'ticker':self.cat.ticker,'score':np.linspace(10,90,len(self.cat)),'return_20d_pct':np.linspace(-10,20,len(self.cat))})
    def test_balance_and_unique(self):
        for strategy in ('혼합형','점수 우선','순환 우선'):
            x=select_candidates(self.cat,self.scores,500,strategy)
            self.assertEqual(len(x),500)
            self.assertEqual(x.ticker.nunique(),500)
            self.assertEqual(x.region.value_counts().to_dict(),{'KR':250,'US':250})
    def test_excluded_etp(self):
        cat=pd.concat([self.cat,pd.DataFrame([{'ticker':'TQQQ','name':'ProShares UltraPro QQQ','market':'NASDAQ','asset_type':'ETF'}])],ignore_index=True)
        self.assertNotIn('TQQQ',set(select_candidates(cat,self.scores,500).ticker))
    def test_stale_excluded(self):
        dates=pd.bdate_range('2025-01-01',periods=90)
        bars=pd.DataFrame({'Close':np.linspace(10,20,90)},index=dates)
        metrics,err=fresh_check(bars,'AAPL',pd.Timestamp('2026-11-13',tz='UTC'))
        self.assertIsNone(metrics);self.assertIn('지연',err)
    def test_rank_uses_new_score(self):
        x=select_candidates(self.cat,self.scores,20)
        f=pd.DataFrame({'ticker':x.ticker,'score':list(range(20)),'return_20d_pct':0,'close':10})
        r=rank_current(x,f)
        self.assertEqual(int(r.iloc[0]['score']),19)
    def test_scenarios(self):
        x=simulate_strategies()
        self.assertEqual(len(x),12)
        self.assertTrue(x['포착률(%)'].between(0,100).all())
if __name__=='__main__':unittest.main()
