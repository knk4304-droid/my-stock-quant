import unittest
import pandas as pd
from model_quality import summarize_archive, archive_issues

class TestArchiveV51(unittest.TestCase):
    def test_missing_columns(self):
        q = summarize_archive(pd.DataFrame({'x':[1]}))
        self.assertEqual(q['invalid_dates'], 1)
        self.assertEqual(q['invalid_prices'], 1)
    def test_date_order(self):
        x = pd.DataFrame({'기록일_KST':['2026-11-09'], '가격기준일':['2026-11-10'], '티커':['ABC'], '기준종가':[10]})
        self.assertEqual(summarize_archive(x)['price_after_record'], 1)
        self.assertIn('가격기준일이 기록일 이후', archive_issues(x)['문제'].tolist())
    def test_valid_dates(self):
        x = pd.DataFrame({'기록일_KST':['2025-01-02'], '가격기준일':['2025-01-01'], '티커':['ABC'], '기준종가':[10]})
        q = summarize_archive(x)
        self.assertEqual(q['invalid_dates'], 0)
        self.assertEqual(q['price_after_record'], 0)
    def test_invalid_and_duplicate(self):
        x = pd.DataFrame({'기록일_KST':['bad','bad'], '가격기준일':['bad','bad'], '티커':['A','A'], '기준종가':[0,1]})
        q = summarize_archive(x)
        self.assertEqual(q['duplicate_keys'], 1)
        self.assertEqual(q['invalid_dates'], 2)
        self.assertEqual(q['invalid_prices'], 1)

if __name__ == '__main__': unittest.main()
