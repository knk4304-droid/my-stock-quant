# batch_update.py - 백그라운드 자동 수집 엔진 (v4.00 완비판)
import datetime
import warnings
import json
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from universe import UniverseLoader
from quant import QuantEngine, fetch_stock_news_sentiment
from data_quality import valid_prices, valid_macro_value

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

    # 1. KOSPI & KOSDAQ (yfinance 1차 -> 네이버 API 2차)
    kr_targets = {
        'KOSPI': {'yf': '^KS11', 'naver': 'KOSPI'},
        'KOSDAQ': {'yf': '^KQ11', 'naver': 'KOSDAQ'}
    }
    for key, cfg in kr_targets.items():
        success = False
        try:
            hist = yf.Ticker(cfg['yf']).history(period='5d', timeout=4)
            if not hist.empty and len(hist) >= 1:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else curr
                rate = round(((curr - prev) / prev) * 100, 2) if prev > 0 else 0.0
                macro_results[key] = {'val': round(curr, 2), 'change': rate}
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
                pass

    # 2. 원/달러 환율 (yfinance 1차 -> 네이버 API 2차)
    fx_success = False
    try:
        fx_hist = yf.Ticker("USDKRW=X").history(period="5d", timeout=4)
        if not fx_hist.empty and len(fx_hist) >= 1:
            curr_fx = float(fx_hist['Close'].iloc[-1])
            prev_fx = float(fx_hist['Close'].iloc[-2]) if len(fx_hist) >= 2 else curr_fx
            rate_fx = round(((curr_fx - prev_fx) / prev_fx) * 100, 2) if prev_fx > 0 else 0.0
            macro_results['USDKRW'] = {'val': round(curr_fx, 2), 'change': rate_fx}
            fx_success = True
    except Exception:
        pass

    if not fx_success:
        try:
            res = requests.get("https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic", headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                macro_results['USDKRW'] = {'val': float(data['closePrice'].replace(',', '')), 'change': float(data['fluctuationsRatio'])}
        except Exception:
            pass

    # 3. 해외 주요 지수 (S&P500, 나스닥, VIX)
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
            if not hist.empty and len(hist) >= 1:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else curr
                rate = round(((curr - prev) / prev) * 100, 2) if prev > 0 else 0.0
                macro_results[key] = {'val': round(curr, 2), 'change': rate}
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
                pass

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
        if not valid_prices(df, 6):
            df = yf.Ticker(ticker).history(period='1mo', timeout=5)
    except Exception:
        df = pd.DataFrame()

    if not valid_prices(df, 6):
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
        '티커': ticker,
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

    # Preserve the first market assignment and avoid repeated provider requests.
    # One security may appear in multiple index universes. Keep the first category,
    # and request its price only once (not once per index membership).
    ticker_market = {}
    for market, tickers in universe.items():
        for ticker in tickers:
            ticker_market.setdefault(ticker, market)
    tasks = list(ticker_market.items())
    results = []
    failures = Counter()
    if not tasks:
        raise RuntimeError('Empty ticker universe; previous data preserved')

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
                else:
                    failures['no_data_or_scoring_error'] += 1
            except Exception as exc:
                failures[type(exc).__name__] += 1

    if not results:
        raise RuntimeError("No stock data collected; previous data preserved")

    # Prevent accidental publication of a nearly empty universe after an API outage.
    if len(results) < max(10, int(len(tasks) * 0.50)):
        raise RuntimeError(f"Insufficient coverage: {len(results)}/{len(tasks)}; previous data preserved")
    df_results = pd.DataFrame(results)
    # Never publish a partially duplicated result set.
    # Defensive check: repeated symbols are a data issue; distinct symbols can
    # legitimately share an external URL, so do not reject solely on URL.
    if '티커' in df_results.columns and df_results['티커'].duplicated().any():
        raise RuntimeError('Duplicate ticker symbols in batch results; previous data preserved')
    nasdaq_data = macro.get('나스닥', macro.get('NASDAQ 100', {}))

    macro_df = pd.DataFrame([{
        'updated_at': now_str,
        'kospi_val': macro.get('KOSPI', {}).get('val'),
        'kospi_chg': macro.get('KOSPI', {}).get('change', 0.0),
        'kosdaq_val': macro.get('KOSDAQ', {}).get('val'),
        'kosdaq_chg': macro.get('KOSDAQ', {}).get('change', 0.0),
        'sp500_val': macro.get('S&P 500', {}).get('val'),
        'sp500_chg': macro.get('S&P 500', {}).get('change', 0.0),
        'nasdaq_val': nasdaq_data.get('val'),
        'nasdaq_chg': nasdaq_data.get('change', 0.0),
        'usdkrw_val': macro.get('USDKRW', {}).get('val'),
        'usdkrw_chg': macro.get('USDKRW', {}).get('change', 0.0),
        'vix_val': macro.get('VIX', {}).get('val'),
        'vix_chg': macro.get('VIX', {}).get('change')
    }])

    # Require a minimum set of real market observations before replacing published files.
    required = ('KOSPI', 'KOSDAQ', 'S&P 500', 'USDKRW', 'VIX')
    missing = [k for k in required if not valid_macro_value(macro.get(k, {}).get('val'))]
    if missing:
        raise RuntimeError(f"Missing macro data {missing}; previous data preserved")
    print(f'Coverage: {len(results)}/{len(tasks)} ({len(results)/len(tasks):.1%}); failures={dict(failures)}')
    df_results.to_parquet('quant_stocks.parquet.tmp', index=False, engine='pyarrow')
    macro_df.to_parquet('quant_macro.parquet.tmp', index=False, engine='pyarrow')
    from pathlib import Path
    Path('quant_stocks.parquet.tmp').replace('quant_stocks.parquet')
    Path('quant_macro.parquet.tmp').replace('quant_macro.parquet')
    # Report is written only after both data files are successfully published.
    report = {'updated_at': now_str, 'requested': len(tasks), 'saved': len(results),
              'coverage': round(len(results)/len(tasks), 4),
              'failed': len(tasks)-len(results), 'failure_types': dict(failures),
              'missing_macro': missing}
    Path('batch_status.json.tmp').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    Path('batch_status.json.tmp').replace('batch_status.json')

    print(f"[{now_str}] ✅ 성공적으로 {len(df_results)}개 종목 수집 및 Parquet 저장 완료!")


if __name__ == "__main__":
    execute_batch_update()
