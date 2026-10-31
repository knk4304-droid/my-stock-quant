# batch_update.py - 백그라운드 자동 수집 엔진 (v4.00 완비판)
import datetime
import warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from universe import UniverseLoader
from quant import QuantEngine, fetch_stock_news_sentiment

warnings.filterwarnings('ignore')

FEATURE_NAMES = [
    '성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀',
    '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성'
]

POS_KW = ['수주', '흑자', '최대실적', '상승', '호실적', '신기술', '특허', '강세', '인수', '호재']
NEG_KW = ['적자', '감소', '유상증자', '하락', '소송', '악재', '부진', '횡령', '이탈', '경고', '리스크']


def get_chart_link(ticker, stock_name):
    clean_code = ticker.split('.')[0]
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        return f"https://finance.naver.com/item/main.naver?code={clean_code}"
    return f"https://finance.yahoo.com/quote/{ticker}"


def fetch_realtime_macro():
    macro_results = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        res = requests.get("https://m.stock.naver.com/api/index/KOSPI/basic", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            macro_results['KOSPI'] = {'val': float(data['closePrice'].replace(',', '')), 'change': float(data['fluctuationsRatio'])}
        else:
            macro_results['KOSPI'] = {'val': 5730.74, 'change': -3.48}
    except Exception:
        macro_results['KOSPI'] = {'val': 5730.74, 'change': -3.48}

    try:
        res = requests.get("https://m.stock.naver.com/api/index/KOSDAQ/basic", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            macro_results['KOSDAQ'] = {'val': float(data['closePrice'].replace(',', '')), 'change': float(data['fluctuationsRatio'])}
        else:
            macro_results['KOSDAQ'] = {'val': 724.38, 'change': -3.83}
    except Exception:
        macro_results['KOSDAQ'] = {'val': 724.38, 'change': -3.83}

    try:
        res = requests.get("https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            macro_results['USDKRW'] = {'val': float(data['closePrice'].replace(',', '')), 'change': float(data['fluctuationsRatio'])}
        else:
            macro_results['USDKRW'] = {'val': 1340.00, 'change': 0.0}
    except Exception:
        macro_results['USDKRW'] = {'val': 1340.00, 'change': 0.0}

    us_targets = {
        'S&P 500': {'yf': '^GSPC', 'naver': 'SPI@SPX'},
        '나스닥': {'yf': '^IXIC', 'naver': 'NAS@IXIC'},
        'NASDAQ 100': {'yf': '^NDX', 'naver': 'NAS@NDX'},
        'VIX': {'yf': '^VIX', 'naver': 'SPI@VIX'}
    }

    for key, cfg in us_targets.items():
        success = False
        try:
            hist = yf.Ticker(cfg['yf']).history(period='5d', timeout=4)
            if hist.empty or len(hist) < 2:
                hist = yf.Ticker(cfg['yf']).history(period='1mo', timeout=4)
                
            if not hist.empty and len(hist) >= 1:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else curr
                rate = round(((curr - prev) / prev) * 100, 2) if prev > 0 else 0.0
                macro_results[key] = {'val': curr, 'change': rate}
                success = True
        except Exception:
            pass

        if not success:
            try:
                res = requests.get(f"https://m.stock.naver.com/api/index/{cfg['naver']}/basic", headers=headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    macro_results[key] = {'val': float(data['closePrice'].replace(',', '')), 'change': float(data['fluctuationsRatio'])}
            except Exception:
                macro_results[key] = {'val': 0.0, 'change': 0.0}

    return macro_results


def process_single_stock(ticker, market, name_map, engine, macro):
    clean_code = ticker.split('.')[0]
    raw_name = name_map.get(ticker, name_map.get(clean_code, None))
    
    if raw_name and raw_name != clean_code:
        if raw_name.endswith(f"({clean_code})"):
            stock_name = raw_name
        else:
            base_name = raw_name.split('(')[0].strip()
            stock_name = f"{base_name} ({clean_code})"
    else:
        stock_name = f"{ticker} ({clean_code})" if ticker != clean_code else clean_code

    df = pd.DataFrame()
    try:
        df = yf.Ticker(ticker).history(period='1y', timeout=5)
        if df.empty or len(df.dropna()) < 2:
            df = yf.Ticker(ticker).history(period='1mo', timeout=5)
    except Exception:
        df = pd.DataFrame()

    if df.empty or len(df.dropna()) < 2:
        return None

    news_score, pos_cnt, neg_cnt = fetch_stock_news_sentiment(clean_code)

    try:
        raw_scores = engine.calculate_raw_scores(df, macro, market, stock_name, news_score=news_score)
        r_1w_val, r_today, r_1d, r_2d, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)
    except Exception:
        return None

    try:
        r_1m_val = float(str(r_1m).replace('%', '').replace('+', '').strip())
    except Exception:
        r_1m_val = 0.0

    chart_link = get_chart_link(ticker, stock_name)

    row = {
        '시장': market,
        '종목명': stock_name,
        '차트링크': chart_link,
        'news_score': news_score,
        'news_pos': pos_cnt,
        'news_neg': neg_cnt,
        'r_1w_val': r_1w_val,
        '당일 수익률': r_today,
        '1일 전': r_1d,
        '2일 전': r_2d,
        '1주 수익률': r_1w,
        '1달 수익률': r_1m,
        '3개월 수익률': r_3m,
        '1년 수익률': r_1y,
    }

    for i, fname in enumerate(FEATURE_NAMES):
        score_val = raw_scores[i] if i < len(raw_scores) else 0.0
        row[fname] = np.round(score_val, 1)

    periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']
    for p in periods:
        try:
            row[f"총점_{p}"] = engine.calculate_v3_score(raw_scores, market, p, r_1w_val, r_1m_val, macro, news_score=news_score)
            row[f"미래수익률_{p}"] = engine.calculate_pure_future_return(raw_scores, market, p, r_1w_val, r_1m_val, macro, news_score=news_score)
        except Exception:
            row[f"총점_{p}"] = 50.0
            row[f"미래수익률_{p}"] = 0.0

    return row


def execute_batch_update():
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 🔄 백그라운드 퀀트 데이터 사전 수집 시작...")

    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    macro = fetch_realtime_macro()

    tasks = [(ticker, market) for market, tickers in universe.items() for ticker in tickers]
    results = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(process_single_stock, ticker, market, name_map, engine, macro)
            for ticker, market in tasks
        ]
        for future in futures:
            try:
                res = future.result()
                if res is not None:
                    results.append(res)
            except Exception:
                pass

    if not results:
        print(f"[{now_str}] ⚠️ 수집된 데이터가 없습니다.")
        return

    df_results = pd.DataFrame(results)
    nasdaq_data = macro.get('나스닥', macro.get('NASDAQ 100', {}))

    macro_df = pd.DataFrame([{
        'updated_at': now_str,
        'kospi_val': macro.get('KOSPI', {}).get('val', 0.0),
        'kospi_chg': macro.get('KOSPI', {}).get('change', 0.0),
        'kosdaq_val': macro.get('KOSDAQ', {}).get('val', 0.0),
        'kosdaq_chg': macro.get('KOSDAQ', {}).get('change', 0.0),
        'sp500_val': macro.get('S&P 500', {}).get('val', 0.0),
        'sp500_chg': macro.get('S&P 500', {}).get('change', 0.0),
        'nasdaq_val': nasdaq_data.get('val', 0.0),
        'nasdaq_chg': nasdaq_data.get('change', 0.0),
        'usdkrw_val': macro.get('USDKRW', {}).get('val', 1340.0),
        'usdkrw_chg': macro.get('USDKRW', {}).get('change', 0.0),
        'vix_val': macro.get('VIX', {}).get('val', 15.0),
        'vix_chg': macro.get('VIX', {}).get('change', 0.0)
    }])

    df_results.to_parquet('quant_stocks.parquet', index=False, engine='pyarrow')
    macro_df.to_parquet('quant_macro.parquet', index=False, engine='pyarrow')

    print(f"[{now_str}] ✅ 성공적으로 {len(df_results)}개 종목 수집 및 Parquet 저장 완료!")


if __name__ == "__main__":
    execute_batch_update()
