import unittest
from risk_review import scenario_risk_reward, coverage_message

class TestRiskReview(unittest.TestCase):
    def test_ratio_conservative(self):
        self.assertEqual(scenario_risk_reward('+6.0% ~ +10.0%', '-3.5% ~ -5.5%'), 1.09)
    def test_invalid_scenarios(self):
        self.assertIsNone(scenario_risk_reward('unknown', '-3% ~ -5%'))
        self.assertIsNone(scenario_risk_reward('-1% ~ +5%', '-3% ~ -5%'))
    def test_coverage(self):
        self.assertIn('2개', coverage_message(2))
        self.assertIn('없습니다', coverage_message(0))
    def test_negative(self):
        with self.assertRaises(ValueError): coverage_message(-1)
