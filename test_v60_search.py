import pandas as pd
from stock_search import build_catalog, matches, candidates

base = {'042660.KS':'한화오션','005930.KS':'삼성전자','AAPL':'애플'}
batch = pd.DataFrame([{'티커':'086520.KQ','종목명':'에코프로비엠'}, {'티커':'PLTR','종목명':'팔란티어'}])
cat = build_catalog(base, batch)
assert matches('한화오션',cat)[0][0] == '042660.KS'
assert matches('042660',cat)[0][0] == '042660.KS'
assert matches('에코프로',cat)[0][0] == '086520.KQ'
assert matches('PLTR',cat)[0][0] == 'PLTR'
assert matches('없는종목',cat) == []
assert candidates('삼성전자',cat)[0][0] == '005930.KS'
print('6 search checks passed')
