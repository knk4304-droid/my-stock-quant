import unittest
from universe_membership import membership_map, category_tickers, etf_weights

class UniverseMembershipTests(unittest.TestCase):
    def test_overlap_preserved(self):
        u = {'S&P500':['AAPL','MSFT'], '나스닥100':['AAPL']}
        self.assertEqual(membership_map(u)['AAPL'], {'S&P500','나스닥100'})
        self.assertEqual(category_tickers(u,'S&P500'), {'AAPL','MSFT'})
    def test_missing_category(self):
        self.assertEqual(category_tickers({},'S&P500'),set())
    def test_etf_no_company_fundamentals(self):
        r=etf_weights({'1Y+':[5,5,10,2,3,20,10,20,15,10]})['1Y+']
        self.assertEqual(r[5:9],[0,0,0,0])
        self.assertAlmostEqual(sum(r),100)

if __name__=='__main__': unittest.main()
