"""v4.4 display-only risk and data freshness helpers.

No buy/sell decisions or calibrated probabilities are generated here.
"""
import datetime as dt
import json
import math
from pathlib import Path


def classify_product(ticker, name):
    symbol = str(ticker or '').upper()
    title = str(name or '').upper()
    if any(x in title for x in ('인버스', 'INVERSE', 'BEAR', 'SHORT ETF')):
        return '인버스/레버리지 ETF' if any(x in title for x in ('2X', '3X', '레버리지')) else '인버스 ETF'
    if any(x in title for x in ('레버리지', '2X', '3X', 'ULTRA', 'BULL')):
        return '레버리지 ETF'
    if any(x in title for x in ('ETF', 'TIGER', 'KODEX', 'ACE ', 'SOL ', 'RISE ', 'SPDR', 'ISHARES')):
        return '일반 ETF (추정)'
    return '주식/기타 (추정)'


def risk_notice(product_type):
    if '레버리지' in product_type or '인버스' in product_type:
        return '고위험: 일간 수익률 추종 구조로 장기 보유 시 기초지수 누적수익률과 달라질 수 있음'
    if 'ETF' in product_type:
        return '상품 구조·추종지수·환헤지 여부를 별도 확인'
    return '변동성·유동성·기업 공시를 확인'


def read_batch_status(path='batch_status.json', now=None):
    file = Path(path)
    if not file.is_file():
        return {'state': 'unknown', 'message': '배치 상태 파일이 없어 최신 갱신 여부를 확인할 수 없습니다.'}
    try:
        report = json.loads(file.read_text(encoding='utf-8'))
        saved = int(report['saved'])
        requested = int(report['requested'])
        stamp = dt.datetime.fromisoformat(report['updated_at'])
        if requested <= 0 or saved < 0 or saved > requested:
            raise ValueError('invalid coverage')
        now = now or dt.datetime.now(stamp.tzinfo)
        if now.tzinfo != stamp.tzinfo:
            now = now.replace(tzinfo=stamp.tzinfo)
        age_hours = (now - stamp).total_seconds() / 3600
        state = 'stale' if age_hours > 24 or age_hours < -1 else 'ok'
        return {'state': state, 'saved': saved, 'requested': requested,
                'coverage': saved / requested, 'updated_at': stamp.isoformat(sep=' '),
                'message': f'최근 배치: {stamp:%Y-%m-%d %H:%M} · {saved}/{requested}종목 ({saved/requested:.1%})'}
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError, OverflowError):
        return {'state': 'invalid', 'message': '배치 상태 파일을 해석할 수 없습니다.'}
