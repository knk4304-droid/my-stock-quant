import json

import pandas as pd
import pytest

import batch_update


def test_batch_writes_parquet_and_preserves_it_on_provider_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    symbols = [f'TEST{i}' for i in range(12)]
    monkeypatch.setattr(batch_update.UniverseLoader, 'get_full_universe',
                        lambda: ({'S&P 500': symbols, 'NASDAQ 100': symbols[:2]}, {}))
    macro = {key: {'val': 100, 'change': 0}
             for key in ('KOSPI', 'KOSDAQ', 'S&P 500', 'USDKRW', 'VIX')}
    monkeypatch.setattr(batch_update, 'fetch_realtime_macro', lambda: macro)
    monkeypatch.setattr(batch_update, 'fetch_stock_news_sentiment', lambda ticker: (0, 0, 0))

    index = pd.bdate_range(end=pd.Timestamp.now().normalize() - pd.Timedelta(days=1), periods=260)
    close = pd.Series(range(100, 360), index=index, dtype=float)
    bars = pd.DataFrame({'Close': close, 'Open': close - 1, 'High': close + 2,
                         'Low': close - 2, 'Volume': 1_000_000})

    class Quotes:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, **kwargs):
            return bars.copy() if self.ticker in available else pd.DataFrame()

    available = set(symbols)
    monkeypatch.setattr(batch_update.yf, 'Ticker', Quotes)
    batch_update.execute_batch_update()

    stocks = pd.read_parquet('quant_stocks.parquet')
    assert stocks['티커'].tolist() == symbols
    assert stocks['시장'].eq('S&P 500').all()
    assert {'총점_1W', '총점_1M', '총점_6M', '총점_1Y', '총점_5Y', '총점_10Y', '총점_10Y+'} <= set(stocks)
    assert pd.read_parquet('quant_macro.parquet').loc[0, 'vix_val'] == 100
    assert pd.read_csv('recommendation_history.csv')['티커'].tolist() == symbols
    status = json.loads((tmp_path/'batch_status.json').read_text())
    assert (status['requested'], status['saved']) == (12, 12)

    originals = {file: file.read_bytes() for file in tmp_path.iterdir()}
    available.intersection_update(symbols[:5])
    with pytest.raises(RuntimeError, match='Insufficient coverage: 5/12'):
        batch_update.execute_batch_update()
    assert {file: file.read_bytes() for file in tmp_path.iterdir()} == originals
