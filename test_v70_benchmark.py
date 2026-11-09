import pandas as pd
from benchmark_review_v70 import compare_benchmark, summarize_comparison, benchmark_for_ticker, fetch_benchmark_prices
from performance_review import evaluate

def test_benchmark_alignment_and_costs():
    result = pd.DataFrame([{'티커':'005930.KS','기간':'1~3D','진입기준일':'2026-01-02',
                            '평가기준일':'2026-01-07','비용반영수익률(%)':10.0}])
    bench = pd.DataFrame([{'ticker':'^KS11','date':'2026-01-02','close':100},
                          {'ticker':'^KS11','date':'2026-01-07','close':105}])
    compared = compare_benchmark(result,bench,fee_bps=10)
    assert len(compared)==1
    assert compared.iloc[0]['지수비용반영수익률(%)']==4.8
    assert compared.iloc[0]['초과수익률(%p)']==5.2
    assert summarize_comparison(compared).iloc[0]['비교가능건수']==1
    assert benchmark_for_ticker('AAPL')=='^GSPC'
    assert compare_benchmark(result,bench.iloc[:1]).empty

def test_entry_date_added_and_future_only():
    snap=pd.DataFrame([{'티커':'AAPL','기록시각_UTC':'2026-01-01T00:00:00+00:00'}])
    prices=pd.DataFrame({'ticker':['AAPL']*5,'date':pd.date_range('2026-01-02',periods=5),
                         'close':[100,101,102,103,104]})
    out=evaluate(snap,prices)
    assert out.iloc[0]['진입기준일']=='2026-01-02'

def test_fetch_benchmarks_fake_downloader():
    def fake_download(ticker,**kwargs):
        return pd.DataFrame({'Close':[100,105]},index=pd.date_range('2026-01-02',periods=2))
    out=fetch_benchmark_prices('2026-01-02','2026-01-03',fake_download)
    assert len(out)==4
