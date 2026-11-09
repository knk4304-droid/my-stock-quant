import unittest
from unittest.mock import Mock
import pandas as pd
from market_data import positive_number, rate_from_history, fetch_usdkrw

class MarketDataTests(unittest.TestCase):
    def test_numeric_validation(self):
        self.assertEqual(positive_number('1,420.50'), 1420.5)
        for x in (None, 'x', 'nan', '-1', '0'):
            self.assertIsNone(positive_number(x))

    def test_history(self):
        x=rate_from_history(pd.DataFrame({'Close':[1400.,1428.]}))
        self.assertEqual(x['val'],1428.)
        self.assertEqual(x['change'],2.)

    def test_first_source(self):
        yf=Mock(); yf.Ticker.return_value.history.return_value=pd.DataFrame({'Close':[1400.,1407.]})
        req=Mock()
        self.assertEqual(fetch_usdkrw(yf,req)['val'],1407.)
        req.get.assert_not_called()

    def test_fallback_and_missing(self):
        yf=Mock(); yf.Ticker.return_value.history.return_value=pd.DataFrame()
        req=Mock(); req.get.return_value.json.return_value={'closePrice':'1,456.00','fluctuationsRatio':'-0.4'}
        self.assertEqual(fetch_usdkrw(yf,req)['val'],1456.)
        req.get.side_effect=RuntimeError('network down')
        self.assertIsNone(fetch_usdkrw(yf,req)['val'])

if __name__=='__main__': unittest.main()
