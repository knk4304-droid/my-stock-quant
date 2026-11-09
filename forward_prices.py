"""Optional, on-demand forward closing-price retrieval for point-in-time snapshots."""
from datetime import timedelta
import pandas as pd


def fetch_forward_prices(snapshot, max_tickers=30, lookback_days=730, downloader=None):
    if not {'기록시각_UTC', '티커'}.issubset(snapshot.columns):
        raise ValueError('추천 CSV에는 기록시각_UTC와 티커 열이 필요합니다')
    if not 1 <= max_tickers <= 100:
        raise ValueError('최대 종목 수 범위 오류')
    times = pd.to_datetime(snapshot['기록시각_UTC'], utc=True, errors='coerce')
    now = pd.Timestamp.now(tz='UTC')
    eligible = snapshot.loc[times.notna() & (times <= now) & (times >= now - pd.Timedelta(days=lookback_days)), '티커']
    tickers = list(dict.fromkeys(eligible.dropna().astype(str).str.strip()))
    tickers = [x for x in tickers if x and x.lower() != 'nan'][:max_tickers]
    if not tickers:
        raise ValueError('최근 2년 이내의 유효한 추천 기록이 없습니다')
    if downloader is None:
        import yfinance as yf
        downloader = yf.download
    start = (times[times.notna() & (times <= now) & (times >= now - pd.Timedelta(days=lookback_days))].min() - pd.Timedelta(days=3)).date().isoformat()
    frames=[]; failures=[]
    for ticker in tickers:
        try:
            data = downloader(ticker, start=start, end=(now + pd.Timedelta(days=1)).date().isoformat(), auto_adjust=True, progress=False, threads=False)
            if data is None or data.empty:
                failures.append(ticker);continue
            close = data['Close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            out = pd.DataFrame({'ticker':ticker,'date':pd.to_datetime(close.index, utc=True), 'close':pd.to_numeric(close.values, errors='coerce')})
            out = out.dropna(subset=['close'])
            out = out[out['close']>0]
            if out.empty: failures.append(ticker)
            else: frames.append(out)
        except Exception:
            failures.append(ticker)
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=['ticker','date','close'])
    return result, f'{len(frames)}/{len(tickers)}개 티커 조회 성공; 실패 {len(failures)}개' + (f' ({", ".join(failures[:5])})' if failures else '')


def summarize_returns(result):
    cols=['기간','평가건수','평균수익률(%)','중앙수익률(%)','양의수익률비율(%)']
    if result.empty or not {'기간','비용반영수익률(%)'}.issubset(result.columns):
        return pd.DataFrame(columns=cols)
    grouped=result.groupby('기간', sort=False)['비용반영수익률(%)']
    return pd.DataFrame([{'기간':period,'평가건수':len(values),'평균수익률(%)':round(values.mean(),2),
                          '중앙수익률(%)':round(values.median(),2),
                          '양의수익률비율(%)':round((values>0).mean()*100,1)} for period,values in grouped])
