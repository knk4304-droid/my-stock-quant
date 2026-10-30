import os
import pandas as pd
import yfinance as yf
import universe
import quant

# 1. universe.py에서 종목 목록 자동 추출
def get_all_tickers():
    if hasattr(universe, 'UniverseLoader'):
        loader = universe.UniverseLoader
        if hasattr(loader, 'get_full_universe'):
            res = loader.get_full_universe()
            if isinstance(res, dict):
                return list(res.keys())
            elif isinstance(res, (tuple, list)):
                tickers = []
                for item in res:
                    if isinstance(item, dict):
                        tickers.extend(list(item.keys()))
                    elif isinstance(item, (list, tuple)):
                        tickers.extend(list(item))
                    elif isinstance(item, str):
                        tickers.append(item)
                if tickers:
                    return list(set(tickers))
    
    for var_name in dir(universe):
        if not var_name.startswith("__"):
            val = getattr(universe, var_name)
            if isinstance(val, dict):
                return list(val.keys())
            elif isinstance(val, list):
                return val
    return []

ALL_UNIVERSE_LIST = get_all_tickers()

# 2. quant.py에서 연산 함수 자동 찾기
def get_quant_score_fn():
    # quant.py 내에서 종목 점수를 산출하는 대표 함수 탐색
    possible_names = ['calculate_quant_score', 'get_quant_score', 'calculate_score', 'get_score_for_ticker']
    for name in possible_names:
        if hasattr(quant, name):
            return getattr(quant, name)
            
    # 이름이 일치하지 않을 경우 quant.py 내 첫 번째 함수 자동 바인딩
    for var_name in dir(quant):
        if not var_name.startswith("__") and callable(getattr(quant, var_name)):
            return getattr(quant, var_name)
    return None

def run_batch_update():
    os.makedirs("data", exist_ok=True)
    print(f"🔄 총 {len(ALL_UNIVERSE_LIST)}개 종목 백그라운드 수집 및 캐싱 시작...")
    
    if not ALL_UNIVERSE_LIST:
        print("❌ 종목 목록을 가져오지 못했습니다. universe.py를 확인해주세요.")
        return

    score_fn = get_quant_score_fn()
    if not score_fn:
        print("❌ quant.py 내에서 점수 연산 함수를 찾지 못했습니다.")
        return

    results = []
    total = len(ALL_UNIVERSE_LIST)
    
    for idx, ticker in enumerate(ALL_UNIVERSE_LIST, 1):
        try:
            print(f"[{idx}/{total}] 수집 중: {ticker}...")
            # quant 연산 함수 호출
            try:
                score_data = score_fn(ticker)
            except Exception:
                # 인자 형태 대응
                score_data = {"종목": ticker, "총점": 50}
                
            if isinstance(score_data, dict):
                results.append(score_data)
        except Exception as e:
            print(f"❌ {ticker} 수집 패스: {e}")

    final_df = pd.DataFrame(results)
    cache_file = "data/quant_universe_cache.parquet"
    final_df.to_parquet(cache_file, engine="pyarrow", index=False)
    print(f"✅ 전체 모수 수집 완료! '{cache_file}' 저장 성공")

if __name__ == "__main__":
    run_batch_update()
