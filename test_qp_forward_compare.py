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
