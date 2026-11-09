"""Point-in-time benchmark comparison, with strictly matching entry/exit dates.

The benchmark CSV uses ticker,date,close; ^KS11 for KR-listed securities and
^GSPC for US-listed securities. Missing observations are NOT forward-filled.
"""
import pandas as pd

BENCHMARKS = {'KR': '^KS11', 'US': '^GSPC'}


def benchmark_for_ticker(ticker):
    symbol = str(ticker).strip().upper()
    return BENCHMARKS['KR'] if symbol.endswith(('.KS', '.KQ')) else BENCHMARKS['US']


def compare_benchmark(results, benchmark_prices, fee_bps=0):
    required = {'티커', '기간', '진입기준일', '평가기준일', '비용반영수익률(%)'}
    if not isinstance(results, pd.DataFrame) or not required.issubset(results.columns):
        raise ValueError('성과 CSV에는 티커, 기간, 진입기준일, 평가기준일, 비용반영수익률(%)이 필요합니다')
    if not isinstance(benchmark_prices, pd.DataFrame) or not {'ticker', 'date', 'close'}.issubset(benchmark_prices.columns):
        raise ValueError('지수 CSV에는 ticker,date,close 열이 필요합니다')
    if not 0 <= fee_bps <= 1000:
        raise ValueError('거래비용은 0~1000bp 범위여야 합니다')
    prices = benchmark_prices.copy()
    prices['ticker'] = prices['ticker'].astype('string').str.strip().str.upper()
    prices['date'] = pd.to_datetime(prices['date'], errors='coerce', utc=True).dt.date.astype('string')
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['ticker','date','close'])
    prices = prices[prices['close'] > 0].drop_duplicates(['ticker','date'], keep='last')
    lookup = prices.set_index(['ticker','date'])['close'].to_dict()
    rows = []
    for _, item in results.iterrows():
        benchmark = benchmark_for_ticker(item['티커'])
        start = str(item['진입기준일'])[:10]
        end = str(item['평가기준일'])[:10]
        initial = lookup.get((benchmark,start))
        final = lookup.get((benchmark,end))
        if initial is None or final is None or start >= end:
            continue
        actual = pd.to_numeric(item['비용반영수익률(%)'], errors='coerce')
        if pd.isna(actual):
            continue
        market_return = (float(final)/float(initial)-1)*100 - 2*fee_bps/100
        rows.append({'티커':item['티커'], '기간':item['기간'], '진입기준일':start,
                     '평가기준일':end, '비교지수':benchmark,
                     '종목비용반영수익률(%)':round(float(actual),3),
                     '지수비용반영수익률(%)':round(market_return,3),
                     '초과수익률(%p)':round(float(actual)-market_return,3)})
    return pd.DataFrame(rows, columns=['티커','기간','진입기준일','평가기준일','비교지수',
                     '종목비용반영수익률(%)','지수비용반영수익률(%)','초과수익률(%p)'])


def summarize_comparison(compared, min_samples=20):
    columns=['기간','비교가능건수','평균초과수익률(%p)','중앙초과수익률(%p)','지수초과비율(%)','해석']
    if compared.empty:
        return pd.DataFrame(columns=columns)
    output=[]
    for period, part in compared.groupby('기간', sort=False):
        excess=part['초과수익률(%p)']
        n=len(part)
        output.append({'기간':period,'비교가능건수':n,
                       '평균초과수익률(%p)':round(float(excess.mean()),2),
                       '중앙초과수익률(%p)':round(float(excess.median()),2),
                       '지수초과비율(%)':round(float((excess>0).mean()*100),1),
                       '해석':'표본 부족 · 참고용' if n<min_samples else '관측 비교 · 검증 필요'})
    return pd.DataFrame(output, columns=columns)


def fetch_benchmark_prices(start_date, end_date, downloader=None):
    """Fetch market index closes on demand; date range is inclusive."""
    if downloader is None:
        import yfinance as yf
        downloader = yf.download
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    if end < start or (end-start).days > 760:
        raise ValueError('지수 조회 기간은 최대 760일입니다')
    frames=[]
    for ticker in BENCHMARKS.values():
        try:
            data=downloader(ticker, start=str(start), end=str(end+pd.Timedelta(days=1)),
                            auto_adjust=True, progress=False, threads=False)
            if data is None or data.empty:
                continue
            close=data['Close']
            if isinstance(close,pd.DataFrame):
                close=close.iloc[:,0]
            frame=pd.DataFrame({'ticker':ticker, 'date':pd.to_datetime(close.index).date,
                                'close':pd.to_numeric(close.to_numpy(),errors='coerce')})
            frames.append(frame.dropna(subset=['close']))
        except Exception:
            continue
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=['ticker','date','close'])
