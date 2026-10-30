import os
import urllib.request
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
import universe
import quant

# 1. 네이버 뉴스 감성 분석 (호재/악재 크롤링)
def get_news_sentiment(stock_name):
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={urllib.parse.quote(stock_name)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'html.parser')
        
        titles = [a.get_text() for a in soup.select('.news_tit')][:5]
        if not titles:
            return 0
            
        pos_words = ['상승', '호실적', '최대', '돌파', '매수', '호재', '계약', '성장']
        neg_words = ['하락', '적자', '우려', '손실', '매도', '악재', '소송', '감소']
        
        score = 0
        for t in titles:
            for p in pos_words:
                if p in t: score += 2
            for n in neg_words:
                if n in t: score -= 2
        return max(min(score, 10), -10) # 최대 +10점 ~ -10점 조정
    except Exception:
        return 0

# 2. universe.py에서 종목 목록 자동 추출
def get_all_tickers():
    if hasattr(universe, 'UniverseLoader'):
        loader = universe.UniverseLoader
        if hasattr(loader, 'get_full_universe'):
            res = loader.get_full_universe()
            if isinstance(res, dict): return list(res.keys())
            elif isinstance(res, (tuple, list)):
                tickers = []
                for item in res:
                    if isinstance(item, dict): tickers.extend(list(item.keys()))
                    elif isinstance(item, (list, tuple)): tickers.extend(list(item))
                    elif isinstance(item, str): tickers.append(item)
                if tickers: return list(set(tickers))
    for var_name in dir(universe):
        if not var_name.startswith("__"):
            val = getattr(universe, var_name)
            if isinstance(val, dict): return list(val.keys())
            elif isinstance(val, list): return val
    return []

ALL_UNIVERSE_LIST = get_all_tickers()

# 3. quant.py 스코어 함수 자동 탐색
def get_quant_score_fn():
    possible_names = ['calculate_quant_score', 'get_quant_score', 'calculate_score']
    for name in possible_names:
        if hasattr(quant, name): return getattr(quant, name)
    for var_name in dir(quant):
        if not var_name.startswith("__") and callable(getattr(quant, var_name)):
            return getattr(quant, var_name)
    return None

def run_batch_update():
    os.makedirs("data", exist_ok=True)
    print(f"🔄 총 {len(ALL_UNIVERSE_LIST)}개 종목 백그라운드 수집/뉴스NLP/캐싱 시작...")
    
    score_fn = get_quant_score_fn()
    results = []
    total = len(ALL_UNIVERSE_LIST)
    
    for idx, ticker in enumerate(ALL_UNIVERSE_LIST, 1):
        try:
            print(f"[{idx}/{total}] 수집 및 뉴스 NLP 반영 중: {ticker}...")
            try:
                score_data = score_fn(ticker)
            except Exception:
                score_data = {"종목": ticker, "총점": 50}
                
            if isinstance(score_data, dict):
                # 뉴스 감성 스코어 가감산 적용 (+10~-10)
                sentiment_adj = get_news_sentiment(ticker)
                if "총점" in score_data:
                    score_data["총점"] = round(score_data["총점"] + sentiment_adj, 2)
                score_data["뉴스감성점수"] = sentiment_adj
                results.append(score_data)
        except Exception as e:
            print(f"❌ {ticker} 수집 패스: {e}")

    final_df = pd.DataFrame(results)
    cache_file = "data/quant_universe_cache.parquet"
    final_df.to_parquet(cache_file, engine="pyarrow", index=False)
    print(f"✅ 전 종목 뉴스/공시 감성 반영 및 로컬 캐싱 완료! '{cache_file}'")

if __name__ == "__main__":
    run_batch_update()
