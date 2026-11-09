"""Transparent, descriptive diagnostics for rule-based ranking outputs.

No predictive accuracy is claimed without a dated, out-of-sample evaluation.
"""
import pandas as pd

REQUIRED = ('티커', '기준종가', '가격기준일')


def summarize_archive(history):
    if history is None or history.empty:
        return {'rows': 0, 'tickers': 0, 'dates': 0, 'duplicate_keys': 0, 'invalid_prices': 0, 'future_dated': 0}
    h = history.copy()
    dates = pd.to_datetime(h.get('기록일_KST', pd.Series(index=h.index, dtype='object')), errors='coerce')
    prices = pd.to_numeric(h.get('기준종가', pd.Series(index=h.index, dtype='float64')), errors='coerce')
    keys = ['기록일_KST', '티커']
    duplicate = int(h.duplicated(keys).sum()) if all(k in h for k in keys) else 0
    return {'rows': len(h), 'tickers': int(h['티커'].nunique()) if '티커' in h else 0,
            'dates': int(dates.dt.date.nunique()), 'duplicate_keys': duplicate,
            'invalid_prices': int((prices.isna() | prices.le(0)).sum()),
            'future_dated': int(dates.gt(pd.Timestamp.now()).sum())}


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
