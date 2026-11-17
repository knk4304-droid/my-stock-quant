"""Offline smoke checks for the v5.6 display-only update."""
import unittest
from pathlib import Path

class V55DisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')

    def test_version_and_compact_table(self):
        dashboard=Path(__file__).with_name('simple_dashboard.py').read_text(encoding='utf-8')
        home=Path(__file__).with_name('qp_home_r12.py').read_text(encoding='utf-8')
        self.assertIn('QUANTPILOT Classic',dashboard)
        self.assertIn('show_unified_home(st, fresh',dashboard)
        self.assertIn('추천종목 TOP10',home)
        self.assertIn('스마트폰용 TOP10 간편 보기',home)

    def test_batch_and_live_universe_are_not_conflated(self):
        self.assertIn('배치 저장', self.source)
        self.assertIn('화면 분석', self.source)

if __name__ == '__main__':
    unittest.main()
