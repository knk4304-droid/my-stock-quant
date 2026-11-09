import unittest
import pandas as pd
from batch_coverage_v82 import compare_universes, coverage_by_market

class CoverageTest(unittest.TestCase):
    def test_overlap_and_saved_only(self):
        saved=pd.DataFrame({'티커':['A','B','B','C'],'종목명':['a','b','b','c'],'시장':['US','KR','KR','KR']})
        live=pd.DataFrame({'티커':['A','Z']})
        result=compare_universes(saved,live)
        self.assertEqual(len(result),3)
        self.assertEqual(result['화면 분석 여부'].eq('이번 화면 분석 포함').sum(),1)
        market=coverage_by_market(result)
        self.assertEqual(int(market['저장 종목'].sum()),3)
        self.assertEqual(int(market['저장 목록에만 있음'].sum()),2)
    def test_empty(self):
        self.assertTrue(compare_universes(None,None).empty)
        self.assertTrue(coverage_by_market(pd.DataFrame()).empty)

if __name__=='__main__': unittest.main()
