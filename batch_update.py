# batch_update.py
import os
import urllib.request
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from universe import UniverseLoader
from quant import QuantEngine

def get_news_sentiment(stock_name):
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={urllib.parse.quote(stock_name)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'html.parser')
        
        titles = [a.get_text() for a in soup.select('.news_tit')][:5]
        if not titles: return 0
            
        pos_words = ['상승', '호실적', '최대', '돌파', '매수', '호재', '성장']
        neg_words = ['하락', '적자', '우려', '손실', '매도', '악재', '감소']
        
        score = 0
        for t in titles:
            for p in pos_words:
                if p in t: score += 1.5
            for n in neg_words:
                if n in t: score -= 1.5
        return max(min(score, 10), -10)
    except Exception:
        return 0

def run_batch_update():
    os.makedirs("data", exist_ok=True)
    universe, name_map = UniverseLoader.get_full_universe()
    engine = QuantEngine()
    
    print("🔄 [한글 종목명 중심] 백그라운드 수집 및 캐싱 시작...")
    
    results = []
    total_count = sum(len(tickers) for tickers in universe.values())
    current_idx = 0

    for market, tickers in universe.items():
        for ticker in tickers:
            current_idx += 1
            clean_code = ticker.split('.')[0]
            stock_name = name_map.get(ticker, name_map.get(clean_code, clean_code))
            
            print(f"[{current_idx}/{total_count}] {market} - {stock_name}({ticker}) 수집 중...")
            
            try:
                hist = yf.Ticker(ticker).history(period='1y', timeout=3)
                r_1w_val, r_today, r_1d, r_2d, r_1w, r_1m, r_3m, r_1y = engine.calculate_returns(hist)
                raw_scores = engine.calculate_raw_scores(hist, {}, market, stock_name)
                sentiment = get_news_sentiment(stock_name)
                
                chart_link = f"[{stock_name}](https://finance.naver.com/item/main.naver?code={clean_code})" if ticker.endswith(('.KS', '.KQ')) else f"[{stock_name}](https://finance.yahoo.com/quote/{ticker})"
                
                row = {
                    '시장': market,
                    'ticker': ticker,      # 백테스팅용 영문 티커
                    '종목명': stock_name,  # 한글 정식 종목명
                    '차트링크': chart_link,
                    'r_1w_val': r_1w_val,
                    '당일 수익률': r_today,
                    '1일 전': r_1d, '2일 전': r_2d,
                    '1주 수익률': r_1w, '1달 수익률': r_1m, '3개월 수익률': r_3m, '1년 수익률': r_1y,
                    '뉴스감성점수': sentiment
                }
                
                feature_names = ['성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀', '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성']
                for i, fname in enumerate(feature_names):
                    row[fname] = round(raw_scores[i], 1)
                    
                periods = ['1W', '1M', '6M', '1Y', '5Y', '10Y', '10Y+']
                for p in periods:
                    row[f"총점_{p}"] = round(engine.calculate_v3_score(raw_scores, market, p, r_1w_val, 0.0, {}) + sentiment, 1)
                    row[f"미래수익률_{p}"] = engine.calculate_pure_future_return(raw_scores, market, p, r_1w_val, 0.0, {})
                    
                results.append(row)
            except Exception as e:
                print(f"❌ {ticker} 수집 예외 처리: {e}")

    final_df = pd.DataFrame(results)
    cache_path = "data/quant_universe_cache.parquet"
    final_df.to_parquet(cache_path, engine="pyarrow", index=False)
    print(f"✅ 수집 완료! 캐시 저장 성공: '{cache_path}'")

if __name__ == "__main__":
    run_batch_update()
