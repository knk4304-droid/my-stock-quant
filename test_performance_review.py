import unittest
import pandas as pd
from performance_review import evaluate

class TestPerformanceReview(unittest.TestCase):
    def test_future_only_and_fee(self):
        snap = pd.DataFrame([{'기록시각_UTC':'2026-01-01T12:00:00Z','티커':'ABC','모형추정치_1~3D':5}])
        dates = pd.date_range('2026-01-02', periods=5, tz='UTC')
        prices = pd.DataFrame({'ticker':['ABC']*5,'date':dates,'close':[100,101,102,110,111]})
        out = evaluate(snap, prices, 10)
        self.assertEqual(len(out),1)
        self.assertEqual(out.iloc[0]['기간'],'1~3D')
        self.assertAlmostEqual(out.iloc[0]['실현전수익률(%)'],10)
        self.assertAlmostEqual(out.iloc[0]['비용반영수익률(%)'],9.8)
    def test_missing_prices(self):
        snap = pd.DataFrame([{'기록시각_UTC':'2026-01-01Z','티커':'ABC'}])
        prices = pd.DataFrame(columns=['ticker','date','close'])
        self.assertTrue(evaluate(snap,prices).empty)
    def test_missing_columns(self):
        with self.assertRaises(ValueError): evaluate(pd.DataFrame(),pd.DataFrame())
    def test_reject_invalid_fee(self):
        with self.assertRaises(ValueError): evaluate(pd.DataFrame(),pd.DataFrame(),-1)

if __name__ == '__main__': unittest.main()
