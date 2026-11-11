"""Offline regression tests for score transparency and period-specific guides."""
import unittest
import pandas as pd
from simple_dashboard import rank, score_guide, valid_scenario

class IntegratedReleaseTests(unittest.TestCase):
    def test_missing_inputs_are_visible(self):
        data = pd.DataFrame([{'score':80, 'return_5d_pct':4, 'return_20d_pct':8, 'volatility_annual':.4},
                             {'score':80, 'return_5d_pct':None, 'return_20d_pct':8, 'volatility_annual':.4}])
        out=rank(data,'스윙 (1~2주)')
        self.assertEqual(set(out['점수 입력 완전성']), {'4/4','3/4'})
        self.assertAlmostEqual(out.iloc[0]['추천 참고점수'],47.4)
    def test_period_formulas_differ(self):
        self.assertNotEqual(score_guide('단기 (1~3일)'),score_guide('스윙 (1~2주)'))
    def test_price_scenario_order(self):
        self.assertTrue(valid_scenario(100,120,90))
        self.assertFalse(valid_scenario(100,95,90))

if __name__=='__main__': unittest.main()
