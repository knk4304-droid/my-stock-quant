"""Point-in-time recommendation export; never claim performance without later prices."""
import datetime as dt
import pandas as pd

PERIODS = ('1~3D','1~2W','1~3M','1Y+')

def coverage_report(frame):
    if frame.empty: return '유효 분석 결과 없음'
    return '표본 기반 분석 (전체 시장 아님)'

def create_snapshot(frame, timestamp=None):
    timestamp = timestamp or dt.datetime.now(dt.timezone.utc).isoformat()
    columns = ['티커','종목명','시장','당일 수익률','1주 수익률']
    for period in PERIODS:
        columns += [f'총점_{period}', f'미래수익률_{period}']
    available = [x for x in columns if x in frame.columns]
    if not {'티커','종목명'}.issubset(frame.columns):
        raise ValueError('추천 기록에 티커와 종목명이 필요합니다')
    result = frame[available].dropna(subset=['티커']).drop_duplicates('티커').copy()
    result.insert(0,'기록시각_UTC', timestamp)
    result.rename(columns={c:c.replace('미래수익률_','모형추정치_') for c in result.columns if c.startswith('미래수익률_')},inplace=True)
    return result
