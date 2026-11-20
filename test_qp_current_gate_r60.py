import pandas as pd
from qp_current_gate_r60 import eligible_refreshed

def test_fresh_accepts_and_stale_rejects():
    now=pd.Timestamp('2026-11-19T08:00:00Z')
    data=pd.DataFrame([{'ticker':'000660.KS','asof_price':'2026-11-19','scanned_at_utc':now},
                       {'ticker':'005930.KS','asof_price':'2026-11-12','scanned_at_utc':now}])
    good, stats=eligible_refreshed(data,now)
    assert good.ticker.tolist()==['000660.KS']
    assert stats['rejected']==1

def test_missing_timestamp_fail_closed():
    now=pd.Timestamp('2026-11-19T08:00:00Z')
    good,stats=eligible_refreshed(pd.DataFrame([{'ticker':'AAPL','asof_price':'2026-11-18'}]),now)
    assert good.empty and stats['rejected']==1

def test_old_refresh_timestamp_rejected():
    now=pd.Timestamp('2026-11-19T08:00:00Z')
    good,_=eligible_refreshed(pd.DataFrame([{'ticker':'000660.KS','asof_price':'2026-11-19','scanned_at_utc':'2026-11-19T07:40:00Z'}]),now)
    assert good.empty


def test_reject_previous_session_after_close_and_intraday_bar_before_close():
    from qp_current_gate_r60 import completed_bars, has_current_price

    bars = pd.DataFrame({'Close': [100, 120]}, index=pd.to_datetime(['2026-11-18', '2026-11-19']))
    before = pd.Timestamp('2026-11-19T20:59:00Z')
    after = pd.Timestamp('2026-11-19T21:01:00Z')
    assert completed_bars(bars, 'AAPL', before).Close.tolist() == [100]
    assert has_current_price('AAPL', '2026-11-18', before)
    assert not has_current_price('AAPL', '2026-11-19', before)
    assert not has_current_price('AAPL', '2026-11-18', after)
    assert has_current_price('AAPL', '2026-11-19', after)


def test_thanksgiving_and_early_close():
    from qp_current_gate_r60 import has_current_price

    assert has_current_price('AAPL', '2026-11-25', '2026-11-26T22:00Z')
    assert not has_current_price('AAPL', '2026-11-27', '2026-11-27T17:59Z')
    assert has_current_price('AAPL', '2026-11-27', '2026-11-27T18:01Z')


def test_fallback_catalog_keeps_market_filter_and_excludes_leveraged_etf():
    from qp_home_r12 import refresh_pool

    catalog = pd.DataFrame([
        ('SPY', 'SPDR S&P 500', 'NYSE/OTHER', 'ETF'),
        ('TQQQ', 'ProShares UltraPro QQQ', 'NASDAQ', 'ETF'),
        ('069500.KS', 'KODEX 200', 'KR ETF', 'ETF'),
        ('AAPL', 'Apple', 'NASDAQ', 'STOCK'),
    ], columns=['ticker', 'name', 'market', 'asset_type'])
    result = refresh_pool(pd.DataFrame(), catalog, '미국 ETF', '전체', '2026-11-19')
    assert result.ticker.tolist() == ['SPY']
