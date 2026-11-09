"""Transparent, deterministic display rankings; not calibrated forecasts."""
import numpy as np
import pandas as pd

SORT_OPTIONS = ('🏆 종합 추천순', '🟢 매수 적합순', '🛡️ 안정성 우선순')


def rank_candidates(frame: pd.DataFrame, option: str, limit: int = 10) -> pd.DataFrame:
    if option not in SORT_OPTIONS:
        raise ValueError('지원하지 않는 정렬 옵션')
    if frame.empty:
        return frame.copy()
    data = frame.copy()
    for col in ('총점', '상승신호점수', 'r_1w_val', '수급/거래량', '기술적모멘텀', '대외변동성', '재무건전성'):
        if col not in data:
            data[col] = np.nan
        data[col] = pd.to_numeric(data[col], errors='coerce')
    # No artificial high scores for missing observations.
    data = data.dropna(subset=['총점', '상승신호점수', 'r_1w_val'])
    if data.empty:
        return data
    data['총점'] = data['총점'].clip(0, 100)
    data['상승신호점수'] = data['상승신호점수'].clip(0, 100)
    if option == SORT_OPTIONS[0]:
        columns = ['총점', '상승신호점수']
    elif option == SORT_OPTIONS[1]:
        # Do not elevate overextended (+8%) or sharply falling (-7%) names.
        eligible = data['r_1w_val'].between(-7, 8, inclusive='left') & (data['총점'] >= 50)
        data['진입조건충족'] = eligible
        data['매수검토점수'] = (0.50 * data['상승신호점수'] +
                          0.30 * data['총점'] +
                          0.10 * data['수급/거래량'].fillna(0).clip(0, 100) +
                          0.10 * data['기술적모멘텀'].fillna(0).clip(0, 100))
        columns = ['진입조건충족', '매수검토점수', '총점']
    else:
        # Price-proxy stability, NOT realized volatility or max drawdown.
        data['안정성대용점수'] = (0.45 * data['대외변동성'].fillna(0).clip(0, 100) +
                            0.35 * data['재무건전성'].fillna(0).clip(0, 100) +
                            0.20 * (100 - data['r_1w_val'].abs().mul(5).clip(0, 100)))
        columns = ['안정성대용점수', '총점']
    if '티커' in data:
        data['_tie'] = data['티커'].astype(str)
        columns.append('_tie')
        ascending = [False] * (len(columns) - 1) + [True]
    else:
        ascending = [False] * len(columns)
    return data.sort_values(columns, ascending=ascending, kind='mergesort').head(limit).drop(columns=['_tie'], errors='ignore')
