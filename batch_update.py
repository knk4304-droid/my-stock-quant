import os
import pandas as pd
import yfinance as yf
import universe

# universe.py 내부 구조에서 종목 리스트/딕셔너리 자동 추출
def get_all_tickers():
    # 1. UniverseLoader 클래스가 존재하는 경우
    if hasattr(universe, 'UniverseLoader'):
        loader = universe.UniverseLoader
        if hasattr(loader, 'get_full_universe'):
            res = loader.get_full_universe()
            # 반환값이 딕셔너리인 경우
            if isinstance(res, dict):
                return list(res.keys())
            # 반환값이 튜플/리스트인 경우
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
    
    # 2. universe.py 내부에 정의된 변수 중 리스트나 딕셔너리 검색
    for var_name in dir(universe):
        if not var_name.startswith("__"):
            val = getattr(universe, var_name)
            if isinstance(val, dict):
                return list(val.keys())
            elif isinstance(val, list):
                return val
                
    return []

ALL_UNIVERSE_LIST = get_all_tickers()

def run_batch_update():
    os.makedirs("data", exist_ok=True)
    print(f"🔄 총 {len(ALL_UNIVERSE_LIST)}개 종목 백그라운드 수집 및 캐싱 시작...")
    
    if not ALL_UNIVERSE_LIST:
        print("❌ 종목 목록을 가져오지 못했습니다. universe.py 구조를 확인해주세요.")
        return

    results = []
    total = len(ALL_UNIVERSE_LIST)
    
    from quant import calculate_quant_score
    
    for idx, ticker in enumerate(ALL_UNIVERSE_LIST, 1):
        try:
            print(f"[{idx}/{total}] 수집 중: {ticker}...")
            score_data = calculate_quant_score(ticker)
            results.append(score_data)
        except Exception as e:
            print(f"❌ {ticker} 수집 실패: {e}")

    final_df = pd.DataFrame(results)
    cache_file = "data/quant_universe_cache.parquet"
    final_df.to_parquet(cache_file, engine="pyarrow", index=False)
    print(f"✅ 전체 모수 수집 완료! '{cache_file}' 저장 성공")

if __name__ == "__main__":
    run_batch_update()
