import unittest
import pandas as pd
from forward_prices import fetch_forward_prices, summarize_returns

class TestForwardPrices(unittest.TestCase):
    def test_missing_columns(self):
        with self.assertRaises(ValueError): fetch_forward_prices(pd.DataFrame())
    def test_future_snapshot_rejected(self):
        snap=pd.DataFrame([{'기록시각_UTC':'2099-01-01T00:00:00Z','티커':'AAPL'}])
        with self.assertRaises(ValueError): fetch_forward_prices(snap,downloader=lambda *a,**k:None)
    def test_mock_prices(self):
        snap=pd.DataFrame([{'기록시각_UTC':pd.Timestamp.now(tz='UTC').isoformat(),'티커':'AAPL'}])
        prices=pd.DataFrame({'Close':[10,11]},index=pd.date_range('2026-11-05',periods=2))
        result,status=fetch_forward_prices(snap,downloader=lambda *a,**k:prices)
        self.assertEqual(len(result),2)
        self.assertIn('1/1',status)
    def test_empty_data(self):
        snap=pd.DataFrame([{'기록시각_UTC':pd.Timestamp.now(tz='UTC').isoformat(),'티커':'AAPL'}])
        result,status=fetch_forward_prices(snap,downloader=lambda *a,**k:pd.DataFrame())
        self.assertTrue(result.empty)
        self.assertIn('실패 1개',status)
    def test_summary(self):
        out=summarize_returns(pd.DataFrame({'기간':['1~3D','1~3D'],'비용반영수익률(%)':[2,-1]}))
        self.assertEqual(out.iloc[0]['양의수익률비율(%)'],50)

if __name__=='__main__': unittest.main()
