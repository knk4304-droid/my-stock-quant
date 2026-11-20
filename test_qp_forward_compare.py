import pandas as pd
import pytest

from qp_forward_compare import compare


def test_frozen_pair_uses_next_captured_session_exact_exit_and_costs():
    snapshot = {'model_version': 'R26-baseline', 'at_utc': '2026-11-25T20:00Z',
                'periods': {'swing': [{'ticker': 'AAA', 'price_date': '2026-11-25'}]},
                'challenger_periods': {'swing': [{'ticker': 'BBB', 'price_date': '2026-11-25'}]}}
    prices = pd.DataFrame([
        ('AAA', '2026-11-25', 5), ('AAA', '2026-11-27', 100), ('AAA', '2026-11-30', 110),
        ('BBB', '2026-11-27', 100), ('BBB', '2026-12-01', 140), ('BBB', '2026-11-30', 120),
    ], columns=['ticker', 'date', 'close'])

    assert compare([snapshot], prices, '2026-11-30T20:59Z', 1, 20).iloc[0].status == 'pending'
    assert compare([snapshot], prices.iloc[:-1], '2026-12-01', 1, 20).iloc[0].status == 'missing prices'
    row = compare([snapshot], prices, '2026-12-01', 1, 20).iloc[0]
    assert row.status == 'paired'
    assert row.baseline_pct == pytest.approx(100 * (1.10 * .998 / 1.002 - 1))
    assert row.challenger_pct == pytest.approx(100 * (1.20 * .998 / 1.002 - 1))


def test_drawdown_uses_intermediate_prices_and_requires_complete_path():
    snapshot = {'model_version': 'R26-baseline', 'at_utc': '2026-11-25T20:00Z',
                'periods': {'swing': [{'ticker': 'AAA', 'price_date': '2026-11-25'}]},
                'challenger_periods': {'swing': [{'ticker': 'BBB', 'price_date': '2026-11-25'}]}}
    dates = ['2026-11-27', '2026-11-30', '2026-12-01', '2026-12-02', '2026-12-03', '2026-12-04']
    prices = pd.DataFrame([
        (ticker, date, close)
        for ticker, closes in [('AAA', [100, 120, 90, 100, 110, 115]),
                               ('BBB', [100, 100, 100, 100, 100, 100]),
                               ('^GSPC', [100, 105, 100, 105, 105, 108])]
        for date, close in zip(dates, closes)
    ], columns=['ticker', 'date', 'close'])
    cutoff = '2026-12-05'
    row = compare([snapshot], prices, cutoff, 5, 0).iloc[0]
    assert row.baseline_pct == pytest.approx(15)
    assert row.baseline_mdd_pct == pytest.approx(25)
    assert row.challenger_mdd_pct == 0
    assert row.benchmark_pct == pytest.approx(8)
    assert row.benchmark_mdd_pct == pytest.approx(100 * (1 - 100 / 105))

    row = compare([snapshot], prices.drop(index=2), cutoff, 5, 0).iloc[0]
    assert row.status == 'paired'
    assert pd.isna(row.baseline_mdd_pct)


def test_recorded_evaluation_uses_post_capture_entry_and_timed_observations():
    from qp_forward_compare import archived_quotes, compare_recorded_recommendations

    cutoff = '2026-11-30T22:00Z'
    observations = pd.DataFrame([
        ('AAA', '2026-11-27', 100, '2026-11-27T18:00Z', '2026-11-30', 110, '2026-11-30T22:00Z'),
        ('AAA', '2026-11-25', 50, '2026-11-25T19:00Z', '2026-11-30', 120, '2026-12-01T00:00Z'),
        ('^GSPC', '2026-11-27', 100, '2026-11-27T19:00Z', '2026-11-30', 103, '2026-11-30T22:00Z'),
    ], columns=['ticker', 'asof_price_old', 'close_old', 'scanned_at_utc_old',
                'asof_price_new', 'close_new', 'scanned_at_utc_new'])
    history = pd.DataFrame([
        ('AAA', '단기 (1~3일)', '2026-11-25T20:00Z'),
        ('AAA', '단기 (1~3일)', '2026-11-25T22:00Z'),
    ], columns=['ticker', 'period', 'recorded_at_utc'])
    prices = archived_quotes(observations, cutoff)
    assert set(prices.close) == {100, 110, 103}
    result = compare_recorded_recommendations(history, prices, cutoff, 20)
    assert len(result) == 1
    row = result.iloc[0]
    assert row.status == 'observed'
    assert row.return_pct == pytest.approx(100 * (1.10 * .998 / 1.002 - 1))
    assert row.benchmark_pct == pytest.approx(3)
