import unittest
from unittest.mock import patch
import sys
import types
import pandas as pd
import market_batch_v90 as scanner

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.now=pd.Timestamp('2026-11-24T05:00:00Z')
        self.h=pd.DataFrame({'Close':range(100,180)},index=pd.bdate_range(end='2026-11-23',periods=80))
    def test_primary_current(self):
        with patch.object(scanner.yf,'Ticker') as ticker:
            ticker.return_value.history.return_value=self.h
            self.assertEqual(scanner.scan_one('005930.KS',completed_at=self.now)['price_source'],'Yahoo Finance')
    def test_fallback_not_promoted(self):
        fake=types.SimpleNamespace(DataReader=lambda *args:self.h)
        with patch.dict(sys.modules,{'FinanceDataReader':fake}), patch.object(scanner.yf,'Ticker') as ticker:
            ticker.return_value.history.side_effect=RuntimeError('Too Many Requests')
            with self.assertRaisesRegex(RuntimeError,'Too Many Requests'):
                scanner.scan_one('005930.KS',completed_at=self.now)
    def test_stale_primary_rejected(self):
        with patch.object(scanner.yf,'Ticker') as ticker:
            ticker.return_value.history.return_value=self.h.iloc[:-1]
            self.assertIsNone(scanner.scan_one('AAPL',completed_at=self.now))

if __name__=='__main__': unittest.main()
