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
    assert result.status.tolist() == ['observed', 'duplicate local day']
    row = result.iloc[0]
    assert row.status == 'observed'
    assert row.return_pct == pytest.approx(100 * (1.10 * .998 / 1.002 - 1))
    assert row.benchmark_pct == pytest.approx(3)


def test_recorded_audit_accounts_for_each_row_and_keeps_missing_paths_distinct():
    from qp_forward_compare import compare_recorded_recommendations

    history = pd.DataFrame([
        ('AAA', '스윙', '2026-11-25T20:00Z'),
        ('BBB', '스윙', '2026-11-25T20:00Z'),
        ('DDD', '스윙', '2026-11-25T20:00Z'),
        ('CCC', '중기', '2026-11-25T20:00Z'),
        ('005930.KS', '장기', '2026-11-25T20:00Z'),
        ('EEE', '단기', 'invalid timestamp'),
    ], columns=['ticker', 'period', 'recorded_at_utc'])
    prices = pd.DataFrame([
        ('AAA', '2026-11-27', 100), ('AAA', '2026-12-04', 110),
        ('BBB', '2026-11-27', 100), ('BBB', '2026-11-27', 101),
    ], columns=['ticker', 'date', 'close'])
    result = compare_recorded_recommendations(history, prices, '2026-12-05', 20)
    assert len(result) == len(history)
    assert result.set_index('ticker').status.to_dict() == {
        'AAA': 'missing intermediate closes', 'BBB': 'conflicting closes',
        'DDD': 'no window prices', 'CCC': 'pending', '005930.KS': 'outside evaluation periods',
        'EEE': 'invalid record',
    }
    assert result.return_pct.isna().all()


def test_recorded_ledger_keeps_input_row_ids_and_cost_breakdown():
    from qp_forward_compare import compare_recorded_recommendations

    history = pd.DataFrame([
        ('AAA', '단기', '2026-11-25T22:00Z'),
        ('AAA', '단기', '2026-11-25T19:00Z'),
    ], columns=['ticker', 'period', 'recorded_at_utc'], index=[7, 7])
    prices = pd.DataFrame([
        ('AAA', '2026-11-27', 100), ('AAA', '2026-11-30', 110),
    ], columns=['ticker', 'date', 'close'])
    result = compare_recorded_recommendations(history, prices, '2026-12-01', 20)
    duplicate, evaluated = result.iloc[0], result.iloc[1]
    assert result.source_row.tolist() == [1, 2]
    assert duplicate.status == 'duplicate local day'
    assert duplicate.duplicate_of == 2
    assert pd.isna(duplicate.return_pct)
    assert evaluated.holding_sessions == 1
    assert evaluated.captured_at_utc == pd.Timestamp('2026-11-25T19:00Z')
    assert evaluated.exit_close_at_utc == pd.Timestamp('2026-11-30T21:00Z')
    assert evaluated.gross_return_pct == pytest.approx(10)
    assert evaluated.cost_pp == pytest.approx(10 - evaluated.return_pct)


def test_partial_provider_series_preserves_archive_and_does_not_splice_prices():
    from qp_forward_compare import compare_recorded_recommendations

    history = pd.DataFrame([
        (ticker, '단기', '2026-11-25T19:00Z') for ticker in ('AAA', 'BBB', 'CCC')
    ], columns=['ticker', 'period', 'recorded_at_utc'])
    columns = ['ticker', 'date', 'close']
    archive = pd.DataFrame([
        ('AAA', '2026-11-27', 100), ('AAA', '2026-11-30', 110),
        ('BBB', '2026-11-27', 100), ('CCC', '2026-11-27', 50),
    ], columns=columns)
    provider = pd.DataFrame([
        ('AAA', '2026-11-27', 60), ('BBB', '2026-11-30', 120),
        ('CCC', '2026-11-27', 90), ('CCC', '2026-11-30', 99),
        ('^GSPC', '2026-11-27', 100), ('^GSPC', '2026-11-30', 102),
    ], columns=columns)
    result = compare_recorded_recommendations(history, provider, '2026-12-01', 20, archived=archive)
    rows = result.set_index('ticker')
    assert rows.loc['AAA', 'price_source'] == 'archive'
    assert rows.loc['AAA', 'gross_return_pct'] == pytest.approx(10)
    assert rows.loc['BBB', 'status'] == 'split across price sources'
    assert pd.isna(rows.loc['BBB', 'return_pct'])
    assert rows.loc['CCC', 'price_source'] == 'provided'
    assert rows.loc['CCC', 'gross_return_pct'] == pytest.approx(10)
    assert rows.loc['AAA', 'benchmark_source'] == 'provided'
    assert rows.loc['AAA', 'benchmark_pct'] == pytest.approx(2)
