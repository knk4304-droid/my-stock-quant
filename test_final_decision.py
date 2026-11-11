from datetime import datetime, timezone
from final_decision import screen_candidates, weekly_status


def candidate(ticker='A', buy=100, stop=95, target=115, score=80):
    return {'코드':ticker,'종목명':ticker,'1차 매수가':buy,'손절 기준가':stop,
            '1차 목표가':target,'분석 점수':score,'가격 조건':'정상'}


def test_screen_safely_rejects_bad_data():
    rows=[candidate(),candidate('B',stop=100),candidate('C',buy=float('nan')),
          candidate('D',target=105),candidate('E',score=None)]
    selected, excluded=screen_candidates(rows,{'A':47.4})
    assert [r['코드'] for r in selected]==['A']
    assert len(excluded)==4
    assert selected[0]['매매 의견']=='조건부 관찰 / 주문 보류'


def test_rank_deterministic_and_limit():
    rows=[candidate('B'),candidate('A'),candidate('C',score=75),candidate('D',score=70)]
    selected,_=screen_candidates(rows,max_candidates=3)
    assert [r['코드'] for r in selected]==['A','B','C']


def test_weekly_schedule_freshness():
    now=datetime(2026,11,11,2,tzinfo=timezone.utc)
    old=weekly_status(now,'2026-11-09T00:00:00Z')
    new=weekly_status(now,'2026-11-09T02:00:00Z')
    assert old['status'].endswith('미확인')
    assert new['status'].endswith('확인')
    assert weekly_status(now)['status']=='실행 확인 필요'
