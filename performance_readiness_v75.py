"""Transparent completeness checks for observed (not predicted) recommendation performance."""
import pandas as pd


def readiness_summary(snapshot, prices=None):
    """Assess input coverage without claiming strategy profitability."""
    if not isinstance(snapshot, pd.DataFrame) or snapshot.empty:
        return {'status': '추천 기록 없음', 'records': 0, 'symbols': 0, 'priced_symbols': 0, 'coverage_pct': 0.0, 'notes': ['추천 스냅샷을 먼저 업로드하세요.']}
    names = {str(c).strip().lower(): c for c in snapshot.columns}
    symbol_col = next((names.get(x) for x in ('ticker', '티커', 'symbol') if x in names), None)
    if symbol_col is None:
        return {'status': '형식 확인 필요', 'records': len(snapshot), 'symbols': 0, 'priced_symbols': 0, 'coverage_pct': 0.0, 'notes': ['추천 기록에 ticker 또는 티커 열이 없습니다.']}
    syms = set(snapshot[symbol_col].dropna().astype(str).str.strip().str.upper()) - {'', 'NAN'}
    notes = []
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        notes.append('후속 종가가 없어 실제 성과를 평가할 수 없습니다.')
        return {'status': '후속 가격 대기', 'records': len(snapshot), 'symbols': len(syms), 'priced_symbols': 0, 'coverage_pct': 0.0, 'notes': notes}
    cols = {str(c).strip().lower(): c for c in prices.columns}
    price_symbol = next((cols.get(x) for x in ('ticker', '티커', 'symbol') if x in cols), None)
    date_col = next((cols.get(x) for x in ('date', '날짜', '거래일') if x in cols), None)
    close_col = next((cols.get(x) for x in ('close', '종가') if x in cols), None)
    if None in (price_symbol, date_col, close_col):
        notes.append('후속 가격 CSV에 ticker, date, close 열이 모두 필요합니다.')
        return {'status': '형식 확인 필요', 'records': len(snapshot), 'symbols': len(syms), 'priced_symbols': 0, 'coverage_pct': 0.0, 'notes': notes}
    dates = pd.to_datetime(prices[date_col], errors='coerce', utc=True)
    close = pd.to_numeric(prices[close_col], errors='coerce')
    valid = dates.notna() & close.gt(0)
    observed = set(prices.loc[valid, price_symbol].dropna().astype(str).str.strip().str.upper())
    count = len(syms & observed)
    coverage = round(100 * count / len(syms), 1) if syms else 0.0
    if count < len(syms):
        notes.append(f'유효한 후속 종가가 없는 티커 {len(syms) - count}개. 해당 추천은 성과 평가에서 제외될 수 있습니다.')
    notes.append('티커가 일치해도 추천 이후 서로 다른 거래일 가격이 있어야 실제 수익률을 계산할 수 있습니다.')
    return {'status': '후속 데이터 확인' if count else '후속 가격 대기', 'records': len(snapshot), 'symbols': len(syms), 'priced_symbols': count, 'coverage_pct': coverage, 'notes': notes}
