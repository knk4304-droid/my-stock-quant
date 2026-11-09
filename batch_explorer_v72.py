"""Read-only exploration of stored batch data; never equate scores to live recommendations."""
import pandas as pd

TICKER_COLUMNS = ('티커', 'ticker', 'Ticker', 'symbol', 'Symbol')
NAME_COLUMNS = ('종목명', 'name', 'Name')
MARKET_COLUMNS = ('시장', 'market', 'Market')
PRICE_COLUMNS = ('기준종가', '종가', 'close', 'Close', 'price')

def pick(frame, names):
    return next((name for name in names if name in frame.columns), None)

def prepare_batch(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(), '저장된 배치 데이터가 없습니다.'
    ticker = pick(frame, TICKER_COLUMNS)
    if not ticker:
        return pd.DataFrame(), '배치 파일에 티커 열이 없습니다.'
    work = frame.copy()
    work[ticker] = work[ticker].astype('string').str.strip()
    work = work.loc[work[ticker].notna() & work[ticker].ne('')].drop_duplicates(ticker, keep='last')
    name = pick(work, NAME_COLUMNS)
    market = pick(work, MARKET_COLUMNS)
    price = pick(work, PRICE_COLUMNS)
    out = pd.DataFrame({'티커': work[ticker].astype(str),
                        '종목명': work[name].fillna(work[ticker]).astype(str) if name else work[ticker].astype(str),
                        '시장': work[market].fillna('미분류').astype(str) if market else '미분류'})
    if price:
        out['저장 기준가'] = pd.to_numeric(work[price], errors='coerce')
    return out.reset_index(drop=True), None

def filter_batch(frame, query='', market='전체'):
    work = frame
    if market != '전체':
        work = work.loc[work['시장'].eq(market)]
    if query.strip():
        q = query.strip()
        match = work['티커'].str.contains(q, case=False, regex=False, na=False) | work['종목명'].str.contains(q, case=False, regex=False, na=False)
        work = work.loc[match]
    return work
