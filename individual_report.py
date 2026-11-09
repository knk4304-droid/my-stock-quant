"""On-demand, price-derived individual stock report helpers."""
import math
import re

PERIODS = [('1~3D', '단기 (1~3일)'), ('1~2W', '스윙 (1~2주)'), ('1~3M', '중기 (1~3개월)'), ('1Y+', '장기 (1년 이상)')]


def normalize_symbol(value):
    symbol = str(value or '').strip().upper()
    if re.fullmatch(r'\d{6}', symbol):
        return symbol + '.KS'  # Default exchange; KOSDAQ codes should use .KQ explicitly.
    if re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^]{0,19}', symbol):
        return symbol
    return None


def report_rows(row):
    rows = []
    for code, label in PERIODS:
        score = _number(row.get('총점_' + code))
        if score is None:
            rows.append({'기간': label, '종합 투자 매력도(100점)' : '자료 없음', '종합의견': '판단 보류', '매수 대응': '가격 및 지표 확인', '매도·위험 대응': '보유 비중 및 위험 재점검'})
            continue
        if score >= 70:
            opinion, entry = '상대적 강세', '추격매수보다 조정 후 지지 확인'
        elif score >= 55:
            opinion, entry = '중립·관찰', '추세 개선 및 거래량 확인 후 판단'
        else:
            opinion, entry = '위험 우선', '신규 진입 보류 및 약세 원인 확인'
        rows.append({'기간': label, '종합 투자 매력도(100점)' : round(score, 1), '종합의견': opinion, '매수 대응': entry,
                     '매도·위험 대응': '사전 손실한도 설정·추세 이탈 시 재평가'})
    return rows


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def overall_assessment(row):
    """Explain agreement between period scores without treating them as probabilities."""
    scores = [_number(row.get('총점_' + code)) for code, _ in PERIODS]
    available = [s for s in scores if s is not None]
    if not available:
        return '분석 보류', '유효한 기간별 점수가 없어 종합 판단을 제공하지 않습니다.'
    strong = sum(s >= 70 for s in available)
    weak = sum(s < 55 for s in available)
    if len(available) < 3:
        return '자료 제한', '평가 가능한 기간이 부족하므로 판단을 보류합니다.'
    if strong >= 3:
        return '상대적 강세 · 추격 주의', '여러 기간의 규칙 기반 점수가 강세이나 수익을 보장하지 않습니다. 조정과 거래량을 확인하세요.'
    if weak >= 3:
        return '위험 우선 · 관망', '다수 기간의 점수가 낮아 신규 진입보다 하락 위험 점검을 우선합니다.'
    return '혼조 · 조건부 관찰', '기간별 평가가 엇갈립니다. 진입 전 투자기간과 위험 한도를 먼저 정하세요.'


def price_scenarios(reference_price, target_pct=8.0, stop_pct=4.0):
    """User-defined scenarios, not predicted prices."""
    price = _number(reference_price)
    target = _number(target_pct)
    stop = _number(stop_pct)
    if price is None or price <= 0 or target is None or stop is None or not (0 < target <= 100 and 0 < stop <= 100):
        raise ValueError('기준가와 목표·손실 비율을 확인하세요.')
    return {
        '목표 시나리오 가격': round(price * (1 + target / 100), 2),
        '손실 제한 시나리오 가격': round(price * (1 - stop / 100), 2),
        '가정 손익비': round(target / stop, 2),
    }
