import unittest
import pandas as pd
from batch_explorer_v72 import prepare_batch, filter_batch

class BatchExplorerTests(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(prepare_batch(None)[0].empty)
    def test_dedupe_and_filter(self):
        raw = pd.DataFrame({'티커':['AAPL','AAPL','005930.KS',None], '종목명':['Apple','Apple','삼성전자','x'], '시장':['미국','미국','한국','한국'], '종가':[1,2,70000,0]})
        clean, error = prepare_batch(raw)
        self.assertIsNone(error)
        self.assertEqual(len(clean), 2)
        self.assertEqual(float(clean.loc[clean['티커'].eq('AAPL'), '저장 기준가'].iloc[0]), 2)
        self.assertEqual(len(filter_batch(clean,'삼성','한국')),1)
        self.assertEqual(len(filter_batch(clean,'AAPL','한국')),0)
    def test_missing_ticker(self):
        self.assertIsNotNone(prepare_batch(pd.DataFrame({'foo':[1]}))[1])

if __name__ == '__main__': unittest.main()
