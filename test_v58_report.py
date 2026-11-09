import unittest
from individual_report import normalize_symbol, report_rows

class TestIndividualReport(unittest.TestCase):
    def test_symbols(self):
        self.assertEqual(normalize_symbol('aapl'), 'AAPL')
        self.assertEqual(normalize_symbol('005930'), '005930.KS')
        self.assertEqual(normalize_symbol('086520.KQ'), '086520.KQ')
        self.assertIsNone(normalize_symbol('AAPL; rm -rf'))

    def test_periods_and_missing(self):
        rows = report_rows({'총점_1~3D': 75, '총점_1~2W': 60, '총점_1~3M': 30, '총점_1Y+': float('nan')})
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['종합의견'], '상대적 강세')
        self.assertEqual(rows[-1]['종합의견'], '판단 보류')

if __name__ == '__main__':
    unittest.main()
