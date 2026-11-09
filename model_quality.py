"""Transparent, descriptive diagnostics for rule-based ranking outputs.

No predictive accuracy is claimed without a dated, out-of-sample evaluation.
"""
import pandas as pd

REQUIRED = ('티커', '기준종가', '가격기준일')


def _date_series(frame, column):
    if column not in frame:
        return pd.Series(pd.NaT, index=frame.index, dtype='datetime64[ns]')
    return pd.to_datetime(frame[column].astype('string').str.slice(0, 10), format='%Y-%m-%d', errors='coerce')


def archive_issues(history):
    """Flag anomalies without silently removing any source rows."""
    if history is None or history.empty:
        return pd.DataFrame(columns=['행', '문제'])
    h = history.reset_index(drop=True)
    dates = _date_series(h, '기록일_KST')
    price_dates = _date_series(h, '가격기준일')
    prices = pd.to_numeric(h.get('기준종가', pd.Series(index=h.index, dtype='float64')), errors='coerce')
    ticker = h.get('티커', pd.Series(index=h.index, dtype='string')).astype('string').fillna('').str.strip()
    duplicate = h.duplicated(['기록일_KST', '티커'], keep='first') if {'기록일_KST','티커'}.issubset(h.columns) else pd.Series(False, index=h.index)
    flags = [
        ('기록일 누락/오류', dates.isna()),
        ('가격기준일 누락/오류', price_dates.isna()),
        ('가격기준일이 기록일 이후', price_dates.gt(dates)),
        ('기준가격 누락/비정상', prices.isna() | prices.le(0)),
        ('티커 누락', ticker.eq('')),
        ('동일 날짜·티커 중복', duplicate),
        ('미래 기록일', dates.gt(pd.Timestamp.now().normalize())),
    ]
    rows = []
    for reason, mask in flags:
        for idx in h.index[mask.fillna(False)]:
            rows.append({'행': int(idx) + 2, '문제': reason})
    return pd.DataFrame(rows, columns=['행','문제'])


def summarize_archive(history):
    empty = {'rows': 0, 'tickers': 0, 'dates': 0, 'duplicate_keys': 0,
             'invalid_prices': 0, 'future_dated': 0, 'invalid_dates': 0,
             'price_after_record': 0}
    if history is None or history.empty:
        return empty
    h = history.copy()
    dates = _date_series(h, '기록일_KST')
    price_dates = _date_series(h, '가격기준일')
    prices = pd.to_numeric(h.get('기준종가', pd.Series(index=h.index, dtype='float64')), errors='coerce')
    keys = ['기록일_KST', '티커']
    return {'rows': len(h), 'tickers': int(h['티커'].nunique()) if '티커' in h else 0,
            'dates': int(dates.dt.date.nunique()),
            'duplicate_keys': int(h.duplicated(keys).sum()) if all(k in h for k in keys) else 0,
            'invalid_prices': int((prices.isna() | prices.le(0)).sum()),
            'future_dated': int(dates.gt(pd.Timestamp.now().normalize()).sum()),
            'invalid_dates': int(dates.isna().sum()),
            'price_after_record': int(price_dates.gt(dates).sum())}


def observed_return_stats(results):
    """Observed archive rows are not independent trades or verified trading sessions."""
    columns = ['기간_관측거래일', '표본수', '평균수익률(%)', '중앙수익률(%)', '양의수익률비율(%)']
    if results is None or results.empty:
        return pd.DataFrame(columns=columns)
    x = results.copy()
    x['수익률(%)'] = pd.to_numeric(x['수익률(%)'], errors='coerce')
    x = x.dropna(subset=['수익률(%)', '기간_관측거래일'])
    if x.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for horizon, group in x.groupby('기간_관측거래일', sort=True):
        ret = group['수익률(%)']
        rows.append({'기간_관측거래일': horizon, '표본수': len(ret),
                     '평균수익률(%)': round(float(ret.mean()), 2),
                     '중앙수익률(%)': round(float(ret.median()), 2),
                     '양의수익률비율(%)': round(float(ret.gt(0).mean() * 100), 2)})
    return pd.DataFrame(rows, columns=columns)
