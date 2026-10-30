import unittest

class TestModuleIntegration(unittest.TestCase):
    def test_imports(self):
        """모든 6개 모듈이 에러 없이 상호 import되는지 확인"""
        try:
            import config
            import quant_engine
            import signal_generator
            import macro_analyzer
            import ui_components
            import app  # 메인 파일
            print("✅ 모든 모듈 임포트 성공")
        except ImportError as e:
            self.fail(f"❌ 모듈 로드 실패 (의존성 끊김): {e}")

    def test_data_pipeline(self):
        """데이터 처리 모듈 -> 시그널 생성 모듈 간 파이프라인 흐름 확인"""
        from quant_engine import calculate_quant_score
        from signal_generator import generate_trade_signal

        # 가상 종목 데이터 입력
        sample_stock = {'CAGR': 80, 'ROE': 70, 'STABILITY': 60, 'VALUATION': 90, 'MOMENTUM': 95}
        
        # 1. 퀀트 모듈 호출
        score = calculate_quant_score(sample_stock, 'LARGE_CAP')
        self.assertIsInstance(score, (int, float))

        # 2. 시그널 모듈 연동 확인
        buy_sig, sell_sig = generate_trade_signal(win_rate=85, quant_score=score, weekly_return=4.5)
        self.assertTrue("강력 매수" in buy_sig or "분할 매수" in buy_sig)

if __name__ == '__main__':
    unittest.main()
