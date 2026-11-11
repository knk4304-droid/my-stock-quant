import unittest
from unittest.mock import patch
import simple_dashboard as dash

class FakeSt:
    def __init__(self): self.lines=[]
    def markdown(self, value, **kwargs): self.lines.append(value)
    def subheader(self, value): self.lines.append(value)
    def caption(self, value): self.lines.append(value)
    def info(self, value): self.lines.append(value)

class WeeklyMobileTests(unittest.TestCase):
    def test_cards_escape_external_names(self):
        st=FakeSt()
        dash.mobile_cards(st,[{'종목명':'<script>alert(1)</script>','종목코드':'ABC','추천 참고점수':50,'시장':'NASDAQ','가격 기준일':'2026-11-10'}])
        self.assertNotIn('<script>',st.lines[0]); self.assertIn('&lt;script&gt;',st.lines[0])
    def test_weekly_report_handles_missing_scan(self):
        st=FakeSt(); import pandas as pd
        dash.weekly_brief(st,{},pd.DataFrame(),pd.DataFrame(),'스윙 (1~2주)')
        self.assertTrue(any('확인 불가' in line for line in st.lines))
    def test_weekly_report_candidate_count(self):
        st=FakeSt(); import pandas as pd
        dash.weekly_brief(st,{'attempted':10,'succeeded':8},pd.DataFrame(),pd.DataFrame([{'asof_price':'2026-11-10'}]),'스윙 (1~2주)')
        self.assertTrue(any('8/10' in line for line in st.lines))

if __name__=='__main__': unittest.main()
