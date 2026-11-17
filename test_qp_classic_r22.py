import pandas as pd
from qp_classic_r22 import chart_url, rolling_points, safe_report, strategy_rows, outcome_status
from qp_weekly import apply_outcome, load
from qp_audit_r17 import observations, summarize
from technical_report_v63 import analyze_history

def test_actual_archive_rolling_crosses_monday():
    records=[r for r in load() if '2026-11-12' <= r['slot'][:10] <= '2026-11-17' and pd.Timestamp(r['slot'])<=pd.Timestamp('2026-11-17 12:00',tz='Asia/Seoul')]; group='스윙 (1~2주)|전체|전체'
    d=rolling_points(records,group,'186230.KQ',pd.Timestamp('2026-11-17 12:00',tz='Asia/Seoul'))
    assert len(d)==6 and d.iloc[0]['시각'].startswith('11/12')
    assert d.iloc[-1]['시각'].startswith('11/17')
    assert len(observations(records,group))==60
    assert rolling_points(records,'unknown','X',pd.Timestamp('2026-11-17 12:00',tz='Asia/Seoul')).empty

def test_chart_links():
    assert chart_url('186230.KQ').endswith('code=186230')
    assert chart_url('NVDA').endswith('/NVDA/chart/')

def test_outcome_no_lookahead_and_after_close():
    s={'captured':'2026-11-12T15:00:00+09:00','outcomes':{'A.KS':{}}}
    bars=pd.DataFrame({'Close':[90,100,110]},index=pd.to_datetime(['2026-11-12','2026-11-13','2026-11-16']))
    apply_outcome(s,'A.KS',bars,pd.Timestamp('2026-11-16 15:00',tz='Asia/Seoul'))
    o=s['outcomes']['A.KS']; assert o['base']==100 and '1' not in o
    apply_outcome(s,'A.KS',bars,pd.Timestamp('2026-11-16 17:30',tz='Asia/Seoul'))
    assert o['1']==10 and '5' not in o and '20' not in o
    assert outcome_status(o).startswith('기준가 확보')

def test_us_market_cutoff():
    s={'captured':'2026-11-12T15:00:00+09:00','outcomes':{'A':{}}}
    bars=pd.DataFrame({'Close':[100,110]},index=pd.to_datetime(['2026-11-13','2026-11-16']))
    apply_outcome(s,'A',bars,pd.Timestamp('2026-11-17 05:00',tz='Asia/Seoul'))
    assert '1' not in s['outcomes']['A']
    apply_outcome(s,'A',bars,pd.Timestamp('2026-11-17 08:30',tz='Asia/Seoul'))
    assert s['outcomes']['A']['1']==10

def test_strategy_and_missing_indicators():
    c=pd.Series([100+i*.2 for i in range(80)],index=pd.bdate_range('2026-07-01',periods=80))
    r=analyze_history(pd.DataFrame({'Close':c,'High':c+2,'Low':c-2,'Volume':1000}))
    assert len(strategy_rows(r))==3 and safe_report(r)['손실 제한 참고가']>0
    r['RSI(14)']=None
    assert safe_report(r)['1차 매수 관찰가'] is None
    assert strategy_rows(r)[0]['매수 조건']=='자료 보완 후 판단'
