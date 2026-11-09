import unittest
import pandas as pd
from model_quality import summarize_archive, observed_return_stats

class TestModelQuality(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(summarize_archive(pd.DataFrame())['rows'], 0)
        self.assertTrue(observed_return_stats(pd.DataFrame()).empty)

    def test_duplicates_and_bad_prices(self):
        x = pd.DataFrame({'기록일_KST':['2025-01-01']*2,'티커':['ABC']*2,'기준종가':[10,0]})
        q = summarize_archive(x)
        self.assertEqual(q['duplicate_keys'], 1)
        self.assertEqual(q['invalid_prices'], 1)

    def test_stats(self):
        x = pd.DataFrame({'기간_관측거래일':[1,1,3], '수익률(%)':[5,-1,2]})
        s = observed_return_stats(x)
        self.assertEqual(s.iloc[0]['표본수'], 2)
        self.assertEqual(s.iloc[0]['양의수익률비율(%)'], 50)
        self.assertEqual(s.iloc[0]['평균수익률(%)'], 2)

if __name__ == '__main__': unittest.main()
