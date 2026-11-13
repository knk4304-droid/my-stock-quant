import unittest
import pandas as pd
from qp_recommend_r21 import filtered_candidates, explain, PERIODS
from ranking_options import rank_candidates, SORT_OPTIONS

class UnifiedRecommendationsTests(unittest.TestCase):
    def setUp(self):
        self.df=pd.DataFrame([
            {'티커':'005930.KS','종목명':'삼성전자','총점_1~2W':85,'상승신호점수':75,'r_1w_val':2,'수급/거래량':70,'기술적모멘텀':80},
            {'티커':'AAPL','종목명':'Apple','총점_1~2W':90,'상승신호점수':65,'r_1w_val':12,'수급/거래량':70,'기술적모멘텀':80},
            {'티커':'SPY','종목명':'SPY ETF','총점_1~2W':70,'상승신호점수':65,'r_1w_val':1,'수급/거래량':70,'기술적모멘텀':80}])
    def classify(self,t,n):return 'ETF' if t=='SPY' else '주식'
    def test_kr(self):self.assertEqual(filtered_candidates(self.df,'스윙 1~2주','국내','전체',self.classify)['티커'].tolist(),['005930.KS'])
    def test_us_etf(self):self.assertEqual(filtered_candidates(self.df,'스윙 1~2주','미국','ETF',self.classify)['티커'].tolist(),['SPY'])
    def test_sort(self):
        pool=filtered_candidates(self.df,'스윙 1~2주','전체','전체',self.classify)
        self.assertEqual(rank_candidates(pool,SORT_OPTIONS[0],10).iloc[0]['티커'],'AAPL')
        self.assertEqual(rank_candidates(pool,SORT_OPTIONS[1],10).iloc[0]['티커'],'005930.KS')
    def test_explain(self):self.assertIn('RSI 72',explain({'RSI(14)':72,'MACD 히스토그램':.3,'거래량/20일 평균':1.4},85,75,'조정 대기'))
if __name__=='__main__':unittest.main()
