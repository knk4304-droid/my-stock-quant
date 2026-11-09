"""Daily OHLCV visualization helpers. Observed historical data, not forecasts."""
import pandas as pd


def build_chart_indicators(history):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(), '조회 가능한 가격 데이터가 없습니다.'
    if 'Close' not in history:
        return pd.DataFrame(), '종가(Close) 열이 없습니다.'
    close = pd.to_numeric(history['Close'], errors='coerce')
    idx = pd.to_datetime(history.index, errors='coerce')
    if getattr(idx, 'tz', None) is not None:
        idx = idx.tz_localize(None)
    frame = pd.DataFrame({'거래일': idx, '종가': close.to_numpy()})
    if 'Volume' in history:
        frame['거래량'] = pd.to_numeric(history['Volume'], errors='coerce').to_numpy()
    else:
        frame['거래량'] = float('nan')
    frame = frame.dropna(subset=['거래일', '종가'])
    frame = frame[frame['종가'] > 0].drop_duplicates('거래일', keep='last').sort_values('거래일')
    if len(frame) < 2:
        return pd.DataFrame(), '유효한 거래일이 2일 미만입니다.'
    frame['20일선'] = frame['종가'].rolling(20, min_periods=20).mean()
    frame['60일선'] = frame['종가'].rolling(60, min_periods=60).mean()
    return frame.reset_index(drop=True), None


def trend_summary(frame):
    if frame is None or frame.empty:
        return '데이터 부족'
    last = frame.iloc[-1]
    if pd.isna(last['20일선']) or pd.isna(last['60일선']):
        return '이동평균 비교를 위한 거래일 부족'
    if last['종가'] > last['20일선'] > last['60일선']:
        return '종가 > 20일선 > 60일선 (상승 배열)'
    if last['종가'] < last['20일선'] < last['60일선']:
        return '종가 < 20일선 < 60일선 (하락 배열)'
    return '이동평균선 혼재 (방향 확인 필요)'
