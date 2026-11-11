"""Offline, deterministic and fail-closed weekly candidate screening.

This is a screening aid, not a buy signal. News verification is never inferred
from keyword matches. Input prices are historical reference observations.
"""
import math
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def finite_positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def screen_candidates(reports, reference_scores=None, max_candidates=3, min_rr=1.5):
    """Return sorted candidates and explicit rejection reasons, without IO."""
    reference_scores = reference_scores or {}
    eligible, excluded = [], []
    for r in reports:
        ticker = str(r.get('코드', '')).strip()
        buy = finite_positive(r.get('1차 매수가'))
        stop = finite_positive(r.get('손절 기준가'))
        target = finite_positive(r.get('1차 목표가'))
        technical = finite_positive(r.get('분석 점수'))
        reason = None
        if not ticker:
            reason = '종목코드 누락'
        elif r.get('가격 조건') != '정상' or not (buy and stop and target and stop < buy < target):
            reason = '가격 조건 미충족'
        elif technical is None or technical > 100:
            reason = '기술 점수 누락 또는 범위 오류'
        else:
            rr = (target-buy)/(buy-stop)
            if not math.isfinite(rr) or rr < min_rr:
                reason = '손익비 기준 미달'
        if reason:
            excluded.append({'코드': ticker, '사유': reason})
            continue
        score = reference_scores.get(ticker)
        try:
            score = float(score)
            if not math.isfinite(score): score = None
        except (ValueError, TypeError):
            score = None
        eligible.append({**r, '손익비': round(rr, 2), '추천 참고점수': score,
                         '검증 상태': '뉴스·공시 원문 검증 전', '매매 의견': '조건부 관찰 / 주문 보류'})
    eligible.sort(key=lambda r: (-float(r['분석 점수']), -float(r['손익비']),
                                 -(r['추천 참고점수'] if r['추천 참고점수'] is not None else float('-inf')),
                                 str(r['코드'])))
    return eligible[:max_candidates], excluded


def weekly_status(now=None, latest_scan=None):
    """Report scan freshness without claiming that the schedule ran at 10:00."""
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    local = now.astimezone(KST)
    monday = local.date() - timedelta(days=local.weekday())
    anchor = datetime.combine(monday, datetime.min.time(), KST).replace(hour=10)
    if local < anchor:
        anchor -= timedelta(days=7)
    if latest_scan is None:
        return {'anchor': anchor, 'status': '실행 확인 필요', 'scan': None}
    if isinstance(latest_scan, str):
        latest_scan = datetime.fromisoformat(latest_scan.replace('Z', '+00:00'))
    if latest_scan.tzinfo is None:
        raise ValueError('scan timestamp must be timezone-aware')
    scan = latest_scan.astimezone(KST)
    return {'anchor': anchor, 'scan': scan,
            'status': '이번 주 기준시각 이후 분석 확인' if scan >= anchor else '이번 주 기준시각 이후 분석 미확인'}
