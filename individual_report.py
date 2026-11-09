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
            rows.append({'기간': label, '퀀트점수': '자료 없음', '종합의견': '판단 보류', '매수 대응': '가격 및 지표 확인', '매도·위험 대응': '보유 비중 및 위험 재점검'})
            continue
        if score >= 70:
            opinion, entry = '상대적 강세', '추격매수보다 조정 후 지지 확인'
        elif score >= 55:
            opinion, entry = '중립·관찰', '추세 개선 및 거래량 확인 후 판단'
        else:
            opinion, entry = '위험 우선', '신규 진입 보류 및 약세 원인 확인'
        rows.append({'기간': label, '퀀트점수': round(score, 1), '종합의견': opinion, '매수 대응': entry,
                     '매도·위험 대응': '사전 손실한도 설정·추세 이탈 시 재평가'})
    return rows


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None
