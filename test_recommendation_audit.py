import unittest
import pandas as pd
from recommendation_audit import create_snapshot, coverage_report
class AuditTests(unittest.TestCase):
 def test_deduplicate(self):
  df=pd.DataFrame({'티커':['AAPL','AAPL','MSFT'],'종목명':['애플','애플','MS'],'미래수익률_1~3D':[2,2,3]})
  out=create_snapshot(df,'2026-11-09T00:00:00+00:00')
  self.assertEqual(len(out),2)
  self.assertIn('모형추정치_1~3D',out.columns)
  self.assertNotIn('미래수익률_1~3D',out.columns)
 def test_required_columns(self):
  with self.assertRaises(ValueError): create_snapshot(pd.DataFrame({'티커':['A']}))
 def test_empty_coverage(self):
  self.assertEqual(coverage_report(pd.DataFrame()),'유효 분석 결과 없음')
if __name__=='__main__': unittest.main()
