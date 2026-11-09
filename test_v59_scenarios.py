import unittest
from individual_report import overall_assessment, price_scenarios

class ScenarioTests(unittest.TestCase):
    def test_scenario_math(self):
        r = price_scenarios(10000, 8, 4)
        self.assertEqual(r['목표 시나리오 가격'], 10800)
        self.assertEqual(r['손실 제한 시나리오 가격'], 9600)
        self.assertEqual(r['가정 손익비'], 2)

    def test_invalid_price(self):
        with self.assertRaises(ValueError):
            price_scenarios(0)

    def test_missing_scores(self):
        self.assertEqual(overall_assessment({})[0], '분석 보류')

    def test_strong_scores(self):
        row = {'총점_'+code: 75 for code in ('1~3D', '1~2W', '1~3M', '1Y+')}
        self.assertIn('강세', overall_assessment(row)[0])

if __name__ == '__main__':
    unittest.main()
