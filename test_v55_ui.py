"""Offline smoke checks for the v5.5 display-only update."""
import unittest
from pathlib import Path

class V55DisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')

    def test_version_and_compact_table(self):
        self.assertIn('AI 추천 주식 매매 (v5.5)', self.source)
        self.assertIn("core_cols = ['차트링크'", self.source)
        self.assertIn("with st.expander('📊 세부 평가 지표 전체 보기')", self.source)

    def test_batch_and_live_universe_are_not_conflated(self):
        self.assertIn('배치 저장', self.source)
        self.assertIn('화면 분석', self.source)

if __name__ == '__main__':
    unittest.main()
