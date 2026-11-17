"""Offline regression checks for v5.6 link display and existing controls."""
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name('app.py').read_text(encoding='utf-8')

HOME=Path(__file__).with_name('qp_home_r12.py').read_text(encoding='utf-8')
DASH=Path(__file__).with_name('simple_dashboard.py').read_text(encoding='utf-8')

class V56LinkTests(unittest.TestCase):
    def test_version(self):
        self.assertIn('QP-R26', DASH)
    def test_url_not_markdown(self):
        self.assertIn("'차트링크': link,", SOURCE)
        self.assertNotIn("'차트링크': f\"[{stock_name}]({link})\"", SOURCE)
    def test_link_column_in_both_tables(self):
        self.assertIn("st.column_config.LinkColumn('차트',display_text='차트 열기')", HOME)
        self.assertIn("st.link_button('선택 종목 실시간·지연 차트 열기'", HOME)
    def test_sort_and_details_preserved(self):
        self.assertIn('top=full.head(10)', HOME)
        self.assertIn('render_detail(st,name,ticker,report)', HOME)
        self.assertIn('현재매수유망순', HOME)
    def test_live_and_batch_not_falsely_combined(self):
        self.assertIn('배치 종목 전체가 화면 추천에 포함된 것은 아닙니다.', SOURCE)

if __name__ == '__main__':
    unittest.main()
