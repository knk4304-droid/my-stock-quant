"""Offline regression checks for v5.6 link display and existing controls."""
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name('app.py').read_text(encoding='utf-8')

class V56LinkTests(unittest.TestCase):
    def test_version(self):
        self.assertIn('AI 추천 주식 매매 (v5.9)', SOURCE)
    def test_url_not_markdown(self):
        self.assertIn("'차트링크': link,", SOURCE)
        self.assertNotIn("'차트링크': f\"[{stock_name}]({link})\"", SOURCE)
    def test_link_column_in_both_tables(self):
        self.assertEqual(SOURCE.count("st.column_config.LinkColumn('차트 보기', display_text='차트 열기')"), 2)
    def test_sort_and_details_preserved(self):
        self.assertIn('rank_candidates(cat_df, cat_sort_opt, limit=10)', SOURCE)
        self.assertIn("with st.expander('📊 세부 평가 지표 전체 보기')", SOURCE)
    def test_live_and_batch_not_falsely_combined(self):
        self.assertIn('배치 종목 전체가 화면 추천에 포함된 것은 아닙니다.', SOURCE)

if __name__ == '__main__':
    unittest.main()
