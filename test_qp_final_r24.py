import pandas as pd
from qp_refresh_r23 import refresh_candidates
from qp_weekly import apply_outcome
from pathlib import Path
from release_verification import verify

def test_invalid_and_stale_refresh():
    d=pd.DataFrame({'ticker':['A','B','C','D','E']})
    def fetch(t):
        return dict(score=80,close={'B':-1,'C':float('inf')}.get(t,10),return_5d_pct=1,return_20d_pct=2,volatility_annual=.2,asof_price={'D':'2026-10-01','E':'2026-11-18'}.get(t,'2026-11-17'))
    out,failed=refresh_candidates(d,fetch,now=pd.Timestamp('2026-11-17 22:00Z'))
    assert list(out.ticker)==['A'] and failed==['B','C','D','E']

def test_incomplete_baseline_not_rewritten():
    s={'captured':'2026-11-12T15:00:00+09:00','outcomes':{'A.KS':{'base':100}}}
    bars=pd.DataFrame({'Close':[90,110]},index=pd.to_datetime(['2026-11-13','2026-11-16']))
    apply_outcome(s,'A.KS',bars,pd.Timestamp('2026-11-16 18:00',tz='Asia/Seoul'))
    assert s['outcomes']['A.KS']['base']==100 and '1' not in s['outcomes']['A.KS']

def test_release_gate():
    assert verify(Path(__file__).parent)==0
