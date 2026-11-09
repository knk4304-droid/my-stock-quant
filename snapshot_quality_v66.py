"""Non-predictive quality checks for uploaded recommendation snapshots."""
import pandas as pd


def inspect_snapshot(frame, now=None):
    """Return (metrics, warnings) without changing the input frame."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {'rows': 0, 'unique_tickers': 0}, ['추천 스냅샷이 비어 있습니다.']
    columns = {str(c).strip().lower(): c for c in frame.columns}
    ticker_col = next((columns[k] for k in ('ticker', '티커', 'symbol') if k in columns), None)
    date_col = next((columns[k] for k in ('date', '추천일', 'snapshot_date', 'timestamp', '추천시각', '기록시각_utc') if k in columns), None)
    warnings = []
    metrics = {'rows': len(frame), 'unique_tickers': 0}
    if ticker_col is None:
        warnings.append('티커 열을 찾을 수 없습니다. CSV 형식을 확인하세요.')
    else:
        symbols = frame[ticker_col].astype('string').str.strip().str.upper()
        valid = symbols.notna() & symbols.ne('') & symbols.ne('NAN')
        metrics['unique_tickers'] = int(symbols[valid].nunique())
        invalid = int((~valid).sum())
        if invalid:
            warnings.append(f'티커 누락 {invalid}행: 해당 행은 평가에서 제외될 수 있습니다.')
        if date_col is not None:
            duplicate_count = int(frame.assign(_ticker=symbols, _date=frame[date_col].astype('string')).duplicated(['_ticker', '_date']).sum())
            if duplicate_count:
                warnings.append(f'동일 날짜·티커 중복 {duplicate_count}행: 성과가 중복 집계될 수 있습니다.')
        elif int(symbols[valid].duplicated().sum()):
            warnings.append('같은 티커가 여러 번 등장합니다. 날짜가 다르면 정상일 수 있으니 확인하세요.')
    if date_col is None:
        warnings.append('추천 날짜 열을 찾을 수 없어 추천 이후 가격인지 검증할 수 없습니다.')
    else:
        dates = pd.to_datetime(frame[date_col], errors='coerce', utc=True)
        missing = int(dates.isna().sum())
        if missing:
            warnings.append(f'추천 날짜 해석 불가 {missing}행: 날짜 형식을 확인하세요.')
        valid_dates = dates.dropna()
        if not valid_dates.empty:
            now_ts = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
            if now_ts.tzinfo is None:
                now_ts = now_ts.tz_localize('UTC')
            future = int((valid_dates > now_ts).sum())
            if future:
                warnings.append(f'미래 추천 시각 {future}행: PC 시간대·CSV 날짜를 확인하세요.')
            metrics['first_date'] = valid_dates.min().strftime('%Y-%m-%d')
            metrics['last_date'] = valid_dates.max().strftime('%Y-%m-%d')
    if metrics['unique_tickers'] > 30:
        warnings.append('자동 가격 조회는 최대 30개 티커만 처리합니다. 나머지는 조회되지 않을 수 있습니다.')
    return metrics, warnings
