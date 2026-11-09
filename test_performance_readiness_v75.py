import unittest
import pandas as pd
from performance_readiness_v75 import readiness_summary

class ReadinessTests(unittest.TestCase):
    def test_missing_snapshot(self):
        self.assertEqual(readiness_summary(pd.DataFrame())['status'], '추천 기록 없음')
    def test_missing_prices(self):
        self.assertEqual(readiness_summary(pd.DataFrame({'ticker':['AAPL','MSFT']}))['status'], '후속 가격 대기')
    def test_valid_prices(self):
        s = pd.DataFrame({'ticker':['AAPL','MSFT']})
        p = pd.DataFrame({'ticker':['AAPL','MSFT','AAPL'], 'date':['2026-10-01','bad','2026-10-02'], 'close':[100,200,-1]})
        r = readiness_summary(s,p)
        self.assertEqual(r['priced_symbols'], 1)
        self.assertEqual(r['coverage_pct'], 50.0)
    def test_invalid_columns(self):
        self.assertEqual(readiness_summary(pd.DataFrame({'ticker':['AAPL']}), pd.DataFrame({'x':[1]}))['status'], '형식 확인 필요')

if __name__ == '__main__': unittest.main()
