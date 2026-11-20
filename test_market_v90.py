import pandas as pd
from market_batch_v90 import clean_catalog, technical_score
from market_dashboard_v90 import read_snapshot

def test_catalog():
    d=pd.DataFrame([['AAPL','Apple','NASDAQ','STOCK'],['AAPL','Apple2','NASDAQ','STOCK'],['bad ticker','x','x','x']],columns=['ticker','name','market','asset_type'])
    out=clean_catalog(d)
    assert len(out)==1 and out.iloc[0]['name']=='Apple2'

def test_scoring():
    d=pd.DataFrame({'Close':[100+i*.1 for i in range(90)]},index=pd.date_range('2026-01-01',periods=90))
    r=technical_score(d)
    assert r and 0<=r['score']<=100
    assert technical_score(d.head(30)) is None

def test_no_data():
    state,df=read_snapshot()
    assert isinstance(state,dict) and isinstance(df,pd.DataFrame)


def test_batch_does_not_overwrite_saved_score_with_delayed_price(monkeypatch, tmp_path):
    import market_batch_v90 as batch

    catalog = pd.DataFrame([('AAPL', 'Apple', 'NASDAQ', 'STOCK')], columns=batch.COLS)
    previous = catalog.assign(close=105, score=75, asof_price='2026-11-18',
                              scanned_at_utc='2026-11-18T22:00Z')
    scores = tmp_path/'scores.csv'
    previous.to_csv(scores, index=False)
    original = scores.read_bytes()
    monkeypatch.setattr(batch, 'DATA', tmp_path)
    monkeypatch.setattr(batch, 'load_catalog', lambda: catalog)
    monkeypatch.setattr(batch, 'scan_one', lambda ticker, *, completed_at: {'asof_price': '2000-01-03'})

    state = batch.run(batch_size=1)

    assert (state['succeeded'], state['failed']) == (0, 1)
    assert scores.read_bytes() == original
    assert pd.read_csv(tmp_path/'last_failures.csv').reason.tolist() == ['latest completed session missing']
