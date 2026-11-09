"""Transparent, non-predictive risk diagnostics for displayed trading ideas."""
import math


def scenario_risk_reward(target_range, stop_range):
    """Read positive target and negative stop percentages; no price forecast."""
    import re
    def numbers(s):
        return [float(v) for v in re.findall(r'[+-]?\d+(?:\.\d+)?', str(s))]
    targets, stops = numbers(target_range), numbers(stop_range)
    if len(targets) != 2 or len(stops) != 2 or min(targets) <= 0 or max(stops) >= 0:
        return None
    reward = min(targets)
    risk = max(abs(v) for v in stops)
    if not all(math.isfinite(x) for x in (reward, risk)) or risk <= 0:
        return None
    return round(reward / risk, 2)


def coverage_message(count, requested=10):
    if count < 0:
        raise ValueError('negative count')
    if count == 0:
        return '현재 분석 가능한 후보가 없습니다. 데이터 누락과 후보군 구성을 확인하세요.'
    if count < requested:
        return f'현재 분석 가능한 후보 {count}개만 표시됩니다. 지수 전체 구성종목을 검색한 결과가 아닙니다.'
    return f'현재 분석 가능한 후보 {count}개 중 최대 {requested}개를 표시합니다. 지수 전체 구성종목 검색 결과가 아닙니다.'
