import pandas as pd
from streamlit.testing.v1 import AppTest

import market_batch_v90
import qp_home_r12
import simple_dashboard
import yfinance
from qp_current_gate_r60 import latest_completed_session


def test_empty_saved_scores_refresh_catalog_and_never_reuse_failed_ranking(monkeypatch, tmp_path):
    class OfflineQuote:
        def __init__(self, ticker):
            pass

        def history(self, **kwargs):
            return pd.DataFrame()

    calls = []
    fail = False

    def scan_one(ticker, *, completed_at):
        calls.append(ticker)
        if fail:
            return None
        return {'close': 100, 'score': 80, 'return_5d_pct': 2, 'return_20d_pct': 4,
                'volatility_annual': .15, 'asof_price': str(latest_completed_session(ticker, completed_at))}

    pd.DataFrame([('AAPL', 'Apple', 'NASDAQ', 'STOCK')],
                 columns=['ticker', 'name', 'market', 'asset_type']).to_csv(tmp_path/'catalog.csv', index=False)
    monkeypatch.setattr(yfinance, 'Ticker', OfflineQuote)
    monkeypatch.setattr(market_batch_v90, 'scan_one', scan_one)
    monkeypatch.setattr(qp_home_r12, 'fetch_news', lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(qp_home_r12, 'DATA', tmp_path)
    monkeypatch.setattr(simple_dashboard, 'DATA', tmp_path)

    app = AppTest.from_file('app.py', default_timeout=20).run()
    assert not app.exception
    assert any('최신 가격 기준 재평가 1개' in message.value for message in app.success)
    assert calls == ['AAPL']

    original_report = qp_home_r12.get_technical_report
    monkeypatch.setattr(qp_home_r12, 'get_technical_report', lambda ticker, **kwargs: {
        '조회 티커': ticker, '기준일': str(latest_completed_session(ticker)),
        '기준 종가': 100, 'RSI(14)': 52, 'MACD 히스토그램': 0.4,
        '1차 매수 관찰가': 98, '1차 목표 관찰가': 110, '손실 제한 참고가': 95,
    })
    app.session_state['qp_top10_detail_editor'] = {
        'edited_rows': {0: {'상세 분석': True}}, 'added_rows': [], 'deleted_rows': [],
    }
    app.run()
    assert not app.exception
    assert any('qp-detail13' in markdown.value and 'RSI(14)' in markdown.value
               for markdown in app.markdown)

    monkeypatch.setattr(qp_home_r12, 'get_technical_report', original_report)
    fail = True
    app.button(key='qp_refresh_market').click().run()
    assert not app.exception
    assert not app.success
    assert any('현재 검증된 추천 후보가 없습니다' in message.value for message in app.warning)
    assert calls == ['AAPL', 'AAPL']

    app.radio(key='qp_unified_mode').set_value('🔎 관심종목 검색').run()
    app.text_input[0].set_value('Apple')
    next(button for button in app.button if button.label == '관심종목 분석').click().run()
    assert not app.exception
    assert any('충분한 일별 시세를 확보하지 못했습니다' in message.value for message in app.warning)
