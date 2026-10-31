# batch_update.py - 백그라운드 자동 수집 엔진
import datetime
import warnings
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
import yfinance as yf
from universe import UniverseLoader
from quant import QuantEngine

warnings.filterwarnings('ignore')

FEATURE_NAMES = [
    '성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀',
    '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성'
]

def fetch_realtime_macro():
    macro_results = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # 1) KOSPI
    try:
        res = requests.get("https://m.stock.naver.com/api/index/KOSPI/basic", headers=headers, timeout=5).json()
        macro_results['KOSPI'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['KOSPI'] = {'val': 2600.0, 'change': 0.0}

    # 2) KOSDAQ
    try:
        res = requests.get("https://m.stock.naver.com/api/index/KOSDAQ/basic", headers=headers, timeout=5).json()
        macro_results['KOSDAQ'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['KOSDAQ'] = {'val': 750.0, 'change': 0.0}

    # 3) USDKRW
    try:
        res = requests.get("https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic", headers=headers, timeout=5).json()
        macro_results['USDKRW'] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
    except Exception:
        macro_results['USDKRW'] = {'val': 1340.00, 'change': 0.0}

    # 4) US Markets
    us_targets = {
        'S&P 500': {'naver': 'SPI@SPX', 'yf': '^GSPC'},
        'NASDAQ 100': {'naver': 'NAS@NDX', 'yf': '^NDX'},
        'VIX': {'naver': 'SPI@VIX', 'yf': '^VIX'}
    }

    for key, cfg in us_targets.items():
        success = False
        try:
            res = requests.get(f"https://m.stock.naver.com/api/index/{cfg['naver']}/basic", headers=headers, timeout=5).json()
            macro_results[key] = {'val': float(res['closePrice'].replace(',', '')), 'change': float(res['fluctuationsRatio'])}
            success = True
        except Exception:
            pass

        if not success:
            try:
                hist = yf.Ticker(cfg['yf']).history(period='5d', timeout=5)
                if not hist.empty and len(hist) >= 2:
                    curr, prev = float(hist['Close'].iloc[-1]), float(hist['Close'].iloc[-2])
                    macro_results[key] = {'val': curr, 'change': (curr - prev) / prev * 100}
                else:
                    macro_results[key] = {'val': 0.0, 'change': 0.0}
            except Exception:
                macro_results[key] = {'val': 0.0, 'change': 0.0}

    return macro_results

def process_single_stock(ticker, market, name_map, engine, macro):
    clean_code = ticker.split('.')[0]
    stock_name_only = name_map.get(ticker, name_map.get(clean_code, clean_code))
    
    # [완치 방어 코드] 종목명과 티커 중복 방지 정제 및 기존 변수명(stock_name) 동시 보장
    if stock_name_only != clean_code and not stock_name_only.endswith(f"({clean_code})"):
        stock_name = f"{stock_name_only} ({clean_code})"
    else:
        stock_name = stock_name_only
        
    display_stock_name = stock_name  # 하위 호환성 보장

    df = pd.DataFrame()
    try:
        df = yf.Ticker(ticker).history(period='1y', timeout=5)
        if df.empty or len(df.dropna()) < 2:
            df = yf.Ticker(ticker).history(period='1mo', timeout=5)
    except Exception:
        df = pd.DataFrame()

    # 뉴스 감성 분석 실행
    news_score, pos_cnt, neg_cnt = fetch_stock_news_sentiment(clean_code)

    raw_scores = engine.calculate_raw_scores(df, macro, market, stock_name, news_score=news_score)
    r_1w_val, r_today, r_1d, r_2d, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(df)

    try:
        r_1m_val = float(str(r_1m).replace('%', '').replace('+', ''))
    except Exception:
        r_1m_val = 0.0

    chart_link = get_chart_link(ticker, stock_name)

    row = {
        '시장': market,
        '종목명': stock_name,  # DB에 이름 (티커) 형태로 안전하게 저장
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
        row[fname] = np.round(raw_scores[i], 1)

    periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']
    for p in periods:
        row[f"총점_{p}"] = engine.calculate_v3_score(raw_scores, market, p, r_1w_val, r_1m_val, macro, news_score=news_score)
        row[f"미래수익률_{p}"] = engine.calculate_pure_future_return(raw_scores, market, p, r_1w_val, r_1m_val, macro, news_score=news_score)

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
                if res:
                    results.append(res)
            except Exception:
                pass

    df_results = pd.DataFrame(results)

    macro_df = pd.DataFrame([{
        'updated_at': now_str,
        'kospi_val': macro.get('KOSPI', {}).get('val', 0.0),
        'kospi_chg': macro.get('KOSPI', {}).get('change', 0.0),
        'kosdaq_val': macro.get('KOSDAQ', {}).get('val', 0.0),
        'kosdaq_chg': macro.get('KOSDAQ', {}).get('change', 0.0),
        'sp500_val': macro.get('S&P 500', {}).get('val', 0.0),
        'sp500_chg': macro.get('S&P 500', {}).get('change', 0.0),
        'nasdaq_val': macro.get('NASDAQ 100', {}).get('val', 0.0),
        'nasdaq_chg': macro.get('NASDAQ 100', {}).get('change', 0.0),
        'usdkrw_val': macro.get('USDKRW', {}).get('val', 1340.0),
        'usdkrw_chg': macro.get('USDKRW', {}).get('change', 0.0),
        'vix_val': macro.get('VIX', {}).get('val', 15.0),
        'vix_chg': macro.get('VIX', {}).get('change', 0.0)
    }])

    # Parquet 저장 (pyarrow 명시)
    df_results.to_parquet('quant_stocks.parquet', index=False, engine='pyarrow')
    macro_df.to_parquet('quant_macro.parquet', index=False, engine='pyarrow')

    print(f"[{now_str}] ✅ 성공적으로 {len(df_results)}개 종목 수집 및 Parquet 저장 완료!")


if __name__ == "__main__":
    execute_batch_update()

# 긍정 / 부정 키워드 사전
POS_KW = ['수주', '흑자', '최대실적', '상승', '호실적', '신기술', '특허', '강세', '인수', '호재']
NEG_KW = ['적자', '감소', '유상증자', '하락', '소송', '악재', '부진', '횡령', '이탈', '경고', '리스크']

def fetch_stock_news_sentiment(clean_code):
    """종목별 최근 5개 뉴스 헤드라인 감성 분석 (-100pt ~ +100pt)"""
    try:
        url = f"https://finance.naver.com/item/news_news.naver?code={clean_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        titles = [a.text.strip() for a in soup.select('.title a')[:5]]

        if not titles:
            return 0.0, 0, 0

        pos_cnt = sum(1 for t in titles for k in POS_KW if k in t)
        neg_cnt = sum(1 for t in titles for k in NEG_KW if k in t)

        total = pos_cnt + neg_cnt
        if total == 0:
            return 0.0, pos_cnt, neg_cnt

        score = round(((pos_cnt - neg_cnt) / total) * 100, 1)
        return score, pos_cnt, neg_cnt
    except Exception:
        return 0.0, 0, 0
