"""Descriptive, post-recommendation results; not a trading backtest."""
import math
import pandas as pd

PERIOD_ORDER = ('1~3D', '1~2W', '1~3M', '1Y+')


def summarize_verified(result, min_samples=20):
    required = {'기간', '티커', '기록시각_UTC', '비용반영수익률(%)'}
    if not isinstance(result, pd.DataFrame) or result.empty or not required.issubset(result.columns):
        return pd.DataFrame(columns=['기간','평가건수','추천건수','평균수익률(%)','중앙수익률(%)','상승비율(%)','상승비율_95%하한(%)','해석'])
    data = result.copy()
    data['비용반영수익률(%)'] = pd.to_numeric(data['비용반영수익률(%)'], errors='coerce')
    data = data.dropna(subset=['기간','티커','기록시각_UTC','비용반영수익률(%)'])
    data = data.drop_duplicates(['기간','티커','기록시각_UTC'], keep='last')
    rows = []
    for period in PERIOD_ORDER:
        group = data[data['기간'].astype(str) == period]
        if group.empty:
            continue
        returns = group['비용반영수익률(%)']
        n = len(returns)
        positive = int((returns > 0).sum())
        p = positive / n
        z = 1.96
        center = (p + z*z/(2*n))/(1+z*z/n)
        margin = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        lower = max(0.0, center-margin)
        rows.append({'기간':period,'평가건수':n,'추천건수':group[['티커','기록시각_UTC']].drop_duplicates().shape[0],
                     '평균수익률(%)':round(float(returns.mean()),2),
                     '중앙수익률(%)':round(float(returns.median()),2),
                     '상승비율(%)':round(100*p,1),
                     '상승비율_95%하한(%)':round(100*lower,1),
                     '해석':'표본 부족 · 참고용' if n < min_samples else '관측 성과 · 검증 필요'})
    return pd.DataFrame(rows)
