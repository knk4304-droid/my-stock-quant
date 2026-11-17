"""Classic-only UI helpers; no fabricated history or trade signals."""
import math
from urllib.parse import quote
import pandas as pd


def chart_url(ticker):
    t=str(ticker).upper().strip()
    if t.endswith(('.KS','.KQ')) and t[:-3].isdigit():
        return 'https://finance.naver.com/item/main.naver?code='+t[:-3]
    return 'https://finance.yahoo.com/quote/'+quote(t,safe='')+'/chart/'


def rolling_points(records,group,ticker,now,days=7):
    now=pd.Timestamp(now).tz_convert('Asia/Seoul'); start=now-pd.Timedelta(days=days)
    points=[]
    for rec in sorted(records,key=lambda r:pd.Timestamp(r['slot'])):
        slot=pd.Timestamp(rec['slot']).tz_convert('Asia/Seoul')
        if not start<=slot<=now or group not in rec.get('groups',{}): continue
        rows=rec['groups'][group]; match=next((r for r in rows if r['ticker']==ticker),None)
        points.append({'시각':slot.strftime('%m/%d %H:%M'),'순위':match['rank'] if match else 11 if rows else None,'가격':match.get('price') if match else None,'가격 기준일':match.get('price_date') if match else None})
    return pd.DataFrame(points,columns=['시각','순위','가격','가격 기준일'])


def outcome_status(o):
    if '20' in o: return '20일 검증 완료'
    if o.get('status'): return o['status']
    if 'base' in o: return '후속 거래일 관측 중'
    return '추적 대기' if not o.get('last_attempt') else '기준가 미확보 · 재확인 필요'


def safe_report(r):
    if r.get('error'): return r
    r=dict(r)
    keys=['기준 종가','RSI(14)','MACD 히스토그램','ATR(14)','거래량/20일 평균','20일선','60일선']
    try:
        valid=all(math.isfinite(float(r[k])) for k in keys) and float(r['기준 종가'])>0 and float(r['ATR(14)'])>0
        levels=[float(r[k]) for k in ['손실 제한 참고가','2차 매수 관찰가','1차 매수 관찰가','기준 종가','1차 목표 관찰가','2차 목표 관찰가']]
        valid=valid and 0<levels[0] < levels[1] <= levels[2] < levels[3] < levels[4] < levels[5]
    except (KeyError,ValueError,TypeError): valid=False
    if not valid:
        r['종합 의견']='판단 보류 · 지표 또는 가격 조건 부족'
        for k in ['1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가','기준가 대비 손절 거리(%)','종합 점수(100)']: r[k]=None
    return r


def strategy_rows(r):
    r=safe_report(r)
    if r.get('error') or r.get('손실 제한 참고가') is None:
        return [{'기간':p,'매수 조건':'자료 보완 후 판단','매도·위험 관리':'실제 시세 확인'} for p in ('단기 1~3일','스윙 1~2주','중기 1~3개월')]
    a,b,t,u,stop=[float(r[k]) for k in ('1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가')]
    unit=r.get('통화',''); fmt=lambda x:f'{x:,.2f} {unit}'
    return [{'기간':'단기 1~3일','매수 조건':f'5일선 회복·거래량 확인; {fmt(a)} 부근 지지 관찰','매도·위험 관리':f'{fmt(t)} 저항 확인; {fmt(stop)} 이탈 시 재검토'}, {'기간':'스윙 1~2주','매수 조건':f'20일선 지지·MACD 개선; {fmt(a)} / {fmt(b)} 분할 관찰','매도·위험 관리':f'{fmt(t)} / {fmt(u)} 분할 청산 관찰; {fmt(stop)} 위험 기준'}, {'기간':'중기 1~3개월','매수 조건':'60일선·실적·공시 확인 후 진입 검토','매도·위험 관리':'60일 추세 훼손·실적 악화 시 재평가; 단기 관찰가를 중기 목표로 확정하지 않음'}]
