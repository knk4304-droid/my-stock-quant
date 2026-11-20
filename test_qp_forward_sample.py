import pandas as pd

from qp_forward_sample import collect, plan


def test_plan_skips_pending_balances_periods_and_deduplicates_requests():
    history = pd.DataFrame([
        ('AAA', '단기 (1~3일)', '2026-11-25T20:00Z'),
        ('AAA', '스윙 (1~2주)', '2026-11-25T20:00Z'),
        ('BBB', '스윙 (1~2주)', '2026-11-25T20:00Z'),
        ('005930.KS', '단기 (1~3일)', '2026-11-25T20:00Z'),
        ('CCC', '중기 (1~3개월)', '2026-11-25T20:00Z'),
    ], columns=['ticker', 'period', 'recorded_at_utc'])
    cutoff = pd.Timestamp('2026-12-05T00:00Z')
    jobs = plan(history, pd.DataFrame(columns=['ticker', 'date', 'close']), cutoff, limit=3)
    assert set(jobs) == {'AAA', 'BBB', '005930.KS', '^GSPC', '^KS200'}
    assert len(jobs['AAA']) == 6
    assert pd.Timestamp('2026-11-26').date() not in jobs['AAA']


def test_collect_exports_only_expected_dates_and_stops_after_rate_limit():
    cutoff = pd.Timestamp('2026-12-01T00:00Z')
    day = pd.Timestamp('2026-11-30').date()
    jobs = {ticker: {day} for ticker in ('AAA', 'BBB', 'CCC')}
    calls = []

    def fetch(ticker, start, end):
        calls.append((ticker, start, end))
        if ticker == 'BBB':
            raise RuntimeError('Too Many Requests')
        return pd.DataFrame({'Close': [100, 101]},
                            index=pd.to_datetime(['2026-11-30', '2026-12-01']))

    quotes, report = collect(jobs, cutoff, fetch)
    assert quotes.to_dict('records') == [{'ticker': 'AAA', 'date': day, 'close': 100}]
    assert [item[0] for item in calls] == ['AAA', 'BBB']
    assert report['provider_stop_reason'] == 'Yahoo Finance 요청 제한'
