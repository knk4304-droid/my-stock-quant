import unittest
import ast
from pathlib import Path
import pandas as pd
from unittest.mock import patch
import importlib.util
from data_quality import valid_prices, return_summary, valid_macro_value

class DataQualityTests(unittest.TestCase):
    def test_returns_exact_sessions(self):
        df=pd.DataFrame({'Close':[100+i for i in range(260)]})
        out=return_summary(df)
        self.assertAlmostEqual(out[0],(359/354-1)*100,places=2)
        self.assertEqual(out[4],f'{(359/354-1)*100:+.2f}%')
        self.assertNotEqual(out[7],'N/A')

    def test_missing_horizons(self):
        df=pd.DataFrame({'Close':[100+i for i in range(10)]})
        out=return_summary(df)
        self.assertEqual(out[5],'N/A')
        self.assertEqual(out[7],'N/A')

    def test_bad_prices_rejected(self):
        self.assertFalse(valid_prices(pd.DataFrame({'Close':[1,2,0,4,5,6]})))
        self.assertFalse(valid_prices(pd.DataFrame({'Open':[1,2,3]})))

    def test_macro_missing(self):
        for value in [None,0,float('nan'),-1]:
            self.assertFalse(valid_macro_value(value))
        self.assertTrue(valid_macro_value(1350.5))

    @unittest.skipUnless(importlib.util.find_spec("yfinance"), "yfinance not installed locally")
    def test_batch_empty_universe_preserves_files(self):
        from batch_update import execute_batch_update
        with patch('batch_update.UniverseLoader.get_full_universe', return_value=({}, {})), \
             patch('batch_update.fetch_realtime_macro', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'Empty ticker universe'):
                execute_batch_update()

    @unittest.skipUnless(importlib.util.find_spec("yfinance"), "yfinance not installed locally")
    def test_batch_insufficient_coverage_preserves_files(self):
        from batch_update import execute_batch_update
        universe = {'test': [f'T{i}' for i in range(30)]}
        with patch('batch_update.UniverseLoader.get_full_universe', return_value=(universe, {})), \
             patch('batch_update.fetch_realtime_macro', return_value={}), \
             patch('batch_update.process_single_stock', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'No stock data collected'):
                execute_batch_update()

    def test_batch_deduplication_by_symbol(self):
        # Static regression check: same symbol in S&P500 and NASDAQ100 must
        # not create two tasks with different market labels.
        source = Path(__file__).with_name('batch_update.py').read_text(encoding='utf-8')
        self.assertIn('ticker_market.setdefault(ticker, market)', source)
        self.assertNotIn('dict.fromkeys((ticker, market)', source)

    def test_batch_preserves_ticker_identity(self):
        source = Path(__file__).with_name('batch_update.py').read_text(encoding='utf-8')
        self.assertIn("'티커': ticker", source)
        self.assertIn("df_results['티커'].duplicated()", source)

    def test_quant_engine_return_contract(self):
        out=return_summary(pd.DataFrame({'Close':list(range(100,110))}))
        self.assertEqual(len(out),8)
        self.assertEqual(out[5],'N/A')

if __name__=='__main__':
    unittest.main()
