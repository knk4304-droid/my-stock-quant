import unittest
import pandas as pd
from stock_chart_v73 import prepare_close_chart, change_percent

class ChartTest(unittest.TestCase):
    def test_valid(self):
        raw = pd.DataFrame({'Close':[100, 110, 121]}, index=pd.date_range('2026-11-01', periods=3))
        result, err = prepare_close_chart(raw)
        self.assertIsNone(err)
        self.assertEqual(len(result),3)
        self.assertAlmostEqual(change_percent(result),21)
    def test_invalid(self):
        result, err = prepare_close_chart(pd.DataFrame({'Open':[1]}))
        self.assertTrue(result.empty)
        self.assertIsNotNone(err)
    def test_zero_and_duplicate(self):
        raw = pd.DataFrame({'Close':[0, 100, 120]}, index=pd.to_datetime(['2026-11-01','2026-11-02','2026-11-02']))
        result, err = prepare_close_chart(raw)
        self.assertTrue(result.empty)
        self.assertIsNotNone(err)
if __name__=='__main__': unittest.main()
