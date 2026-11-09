import unittest
import pandas as pd
from ranking_options import SORT_OPTIONS, rank_candidates

class RankingTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            {'티커':'A', '총점':90,'상승신호점수':90,'r_1w_val':12,'수급/거래량':80,'기술적모멘텀':90,'대외변동성':20,'재무건전성':30},
            {'티커':'B', '총점':75,'상승신호점수':80,'r_1w_val':1,'수급/거래량':80,'기술적모멘텀':80,'대외변동성':90,'재무건전성':90},
            {'티커':'C', '총점':60,'상승신호점수':60,'r_1w_val':-2,'수급/거래량':50,'기술적모멘텀':50,'대외변동성':40,'재무건전성':50},
        ])
    def test_composite(self):
        self.assertEqual(rank_candidates(self.df,SORT_OPTIONS[0]).iloc[0]['티커'],'A')
    def test_buy_not_overextended(self):
        self.assertEqual(rank_candidates(self.df,SORT_OPTIONS[1]).iloc[0]['티커'],'B')
    def test_stability(self):
        self.assertEqual(rank_candidates(self.df,SORT_OPTIONS[2]).iloc[0]['티커'],'B')
    def test_missing_scores_excluded(self):
        frame = pd.concat([self.df, pd.DataFrame([{'티커':'X','총점':None,'상승신호점수':99,'r_1w_val':0}])],ignore_index=True)
        self.assertNotIn('X',rank_candidates(frame,SORT_OPTIONS[0])['티커'].tolist())
    def test_input_unchanged(self):
        before=self.df.copy(deep=True)
        rank_candidates(self.df,SORT_OPTIONS[1])
        pd.testing.assert_frame_equal(before,self.df)
    def test_bad_option(self):
        with self.assertRaises(ValueError): rank_candidates(self.df,'wrong')
    def test_empty(self):
        self.assertTrue(rank_candidates(self.df.iloc[:0],SORT_OPTIONS[0]).empty)
    def test_limit(self):
        self.assertEqual(len(rank_candidates(self.df,SORT_OPTIONS[0],limit=2)),2)

if __name__ == '__main__': unittest.main()
