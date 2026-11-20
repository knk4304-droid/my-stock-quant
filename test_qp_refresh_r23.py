import pandas as pd
from qp_refresh_r23 import resolve_catalog, refresh_candidates, expected_weekday

def test_symbol():
    c=pd.DataFrame({'ticker':['186230.KQ','005930.KS'],'name':['그린플러스','삼성전자']})
    assert resolve_catalog('그린 플러스',c)=='186230.KQ'
    assert resolve_catalog('186230',c)=='186230.KQ'
    assert resolve_catalog('없는 종목',c)==''
    assert resolve_catalog('NVDA',c)=='NVDA'

def test_refresh():
    d=pd.DataFrame({'ticker':['A','B'],'score':[1,2]})
    def fetch(t):
        if t=='B': raise RuntimeError()
        return dict(score=80,close=10,return_5d_pct=1,return_20d_pct=2,volatility_annual=.2,asof_price='2026-11-17')
    out,failed=refresh_candidates(d,fetch,now=pd.Timestamp('2026-11-17 22:00Z'))
    assert list(out.ticker)==['A'] and failed==['B'] and out.iloc[0].score==80
    assert d.iloc[0].score==1

def test_weekday():
    assert str(expected_weekday(pd.Timestamp('2026-11-16 00:00Z'),True))=='2026-11-16'
    assert str(expected_weekday(pd.Timestamp('2026-11-16 00:00Z'),False))=='2026-11-13'


def test_quote_sweep_does_not_repeat_calls_after_rate_limit():
    import pytest
    from qp_refresh_r23 import QuoteSweep

    calls = []

    def fetch(symbol):
        calls.append(symbol)
        raise RuntimeError('Too Many Requests')

    sweep = QuoteSweep(fetch)
    for symbol in ('A', 'B'):
        with pytest.raises(RuntimeError, match='요청 제한'):
            sweep(symbol)
    assert calls == ['A']


def test_quote_sweep_retries_timeout_only_once(monkeypatch):
    import pytest
    import qp_refresh_r23

    delays = []

    def fetch(symbol):
        raise TimeoutError('read timed out')

    monkeypatch.setattr(qp_refresh_r23, 'sleep', delays.append)
    sweep = qp_refresh_r23.QuoteSweep(fetch)
    with pytest.raises(TimeoutError):
        sweep('A')
    assert delays == [1]
    assert not sweep.stopped.is_set()
