import unittest
import pandas as pd
from chart_insights_v74 import build_chart_indicators, trend_summary

class ChartTests(unittest.TestCase):
    def test_valid_history(self):
        h = pd.DataFrame({'Close': range(1, 81), 'Volume': [100]*80}, index=pd.date_range('2026-01-01', periods=80))
        f, err = build_chart_indicators(h)
        self.assertIsNone(err)
        self.assertEqual(len(f), 80)
        self.assertEqual(trend_summary(f), '종가 > 20일선 > 60일선 (상승 배열)')
    def test_invalid(self):
        f, err = build_chart_indicators(pd.DataFrame())
        self.assertTrue(f.empty)
        self.assertTrue(err)
    def test_short_history(self):
        h = pd.DataFrame({'Close': [10, 11]}, index=pd.date_range('2026-01-01', periods=2))
        f, err = build_chart_indicators(h)
        self.assertIsNone(err)
        self.assertIn('부족', trend_summary(f))

if __name__ == '__main__': unittest.main()
