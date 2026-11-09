import unittest
import pandas as pd
from dashboard_quality_v80 import dashboard_coverage, ranking_safety

class DashboardQualityTests(unittest.TestCase):
    def test_coverage_separates_sources(self):
        live = pd.DataFrame({'티커':['A','B'], '총점':[60,70]})
        batch = pd.DataFrame({'ticker':['B','C','D']})
        out = dashboard_coverage(4, live, batch)
        self.assertEqual((out['live'],out['stored'],out['overlap'],out['stored_only']), (2,3,1,2))
        self.assertEqual(out['live_pct'], 50.0)
    def test_duplicate_and_invalid_score(self):
        x = pd.DataFrame({'티커':['A','A','B'], '총점':[50,None,120]})
        out = ranking_safety(x)
        self.assertEqual((out['duplicate'],out['missing_score']), (1,2))
    def test_empty(self):
        self.assertEqual(dashboard_coverage(0,pd.DataFrame())['live_pct'],0)
        self.assertEqual(ranking_safety(pd.DataFrame())['rows'],0)

if __name__ == '__main__': unittest.main()
