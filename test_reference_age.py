import unittest
import pandas as pd
from qp_home_r12 import reusable_candidates, reference_age

class ReferenceAgeTests(unittest.TestCase):
    def test_period_limits(self):
        self.assertEqual([reference_age(p) for p in ['단기','스윙','중기','장기']], [1,3,5,10])

    def test_prior_session_reference_only(self):
        now=pd.Timestamp('2026-11-24T05:00:00Z')
        frame=pd.DataFrame([dict(ticker='005930.KS',name='삼성전자',market='KOSPI',asset_type='STOCK',score=80,close=70000,return_5d_pct=2,return_20d_pct=4,volatility_annual=.2,asof_price='2026-11-20',scanned_at_utc='2026-11-20T08:00:00Z')])
        self.assertTrue(reusable_candidates(frame,now).empty)
        result=reusable_candidates(frame,now,1)
        self.assertEqual(len(result),1)
        self.assertEqual(result.iloc[0].data_age_sessions,1)
        frame['scanned_at_utc']='2026-11-25T08:00:00Z'
        self.assertTrue(reusable_candidates(frame,now,10).empty)

if __name__=='__main__': unittest.main()
