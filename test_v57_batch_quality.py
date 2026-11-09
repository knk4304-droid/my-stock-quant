import unittest
import pandas as pd
from batch_universe_quality import inspect_batch, load_batch

class BatchQualityTests(unittest.TestCase):
    def test_dedup_and_overlap(self):
        f = pd.DataFrame({'티커':['AAPL','AAPL','005930.KS',None], 'Close':[10,11,0,5]})
        q = inspect_batch(f, ['AAPL','MSFT'])
        self.assertEqual((q['rows'],q['unique'],q['duplicates'],q['overlap'],q['missing_ticker'],q['missing_price']), (4,2,1,1,1,1))
    def test_missing_schema(self):
        q = inspect_batch(pd.DataFrame({'other':[1]}))
        self.assertIsNone(q['ticker_column'])
        self.assertEqual(q['missing_ticker'],1)
    def test_missing_file(self):
        frame, error = load_batch('/nonexistent/path/v57.parquet')
        self.assertIsNone(frame)
        self.assertTrue(error)

if __name__ == '__main__': unittest.main()
