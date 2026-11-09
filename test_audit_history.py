import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
from audit_history import build_daily_observations, append_daily_observations, evaluate_observed_history

class AuditHistoryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,9,9,0,tzinfo=timezone.utc)
        self.batch=pd.DataFrame([{'티커':'AAPL','종목명':'Apple','시장':'US','기준종가':100.0,'가격기준일':'2026-11-06','총점_1W':70}, {'티커':'BAD','기준종가':-1,'가격기준일':'2026-11-06'}])
    def test_invalid_prices_excluded(self):
        result=build_daily_observations(self.batch,self.now)
        self.assertEqual(result['티커'].tolist(),['AAPL'])
    def test_idempotent_same_day(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'history.csv'
            self.assertEqual(append_daily_observations(self.batch,f,self.now)[1],1)
            self.assertEqual(append_daily_observations(self.batch,f,self.now)[1],0)
            self.assertEqual(len(pd.read_csv(f)),1)
    def test_preserve_existing_when_bad(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'history.csv';f.write_text('bad\n')
            with self.assertRaises(ValueError): append_daily_observations(self.batch,f,self.now)
            self.assertEqual(f.read_text(),'bad\n')
    def test_only_future_distinct_market_dates(self):
        days=['2026-11-06','2026-11-06','2026-11-09','2026-11-10','2026-11-11','2026-11-12','2026-11-13']
        h=pd.DataFrame([{'티커':'AAPL','기록일_KST':f'2026-11-{i+9:02d}','기준종가':100+i*2,'가격기준일':day} for i,day in enumerate(days)])
        result=evaluate_observed_history(h)
        self.assertEqual(len(result[result['기간_관측거래일']==1]),5)
        self.assertTrue((result['관측간격_달력일']>0).all())
    def test_future_price_excluded(self):
        frame=self.batch.copy();frame.loc[0,'가격기준일']='2026-11-20'
        self.assertTrue(build_daily_observations(frame,self.now).empty)

if __name__=='__main__': unittest.main()
