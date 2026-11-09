import unittest
import pandas as pd
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

    def test_quant_engine_return_contract(self):
        out=return_summary(pd.DataFrame({'Close':list(range(100,110))}))
        self.assertEqual(len(out),8)
        self.assertEqual(out[5],'N/A')

if __name__=='__main__':
    unittest.main()
