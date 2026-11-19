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
