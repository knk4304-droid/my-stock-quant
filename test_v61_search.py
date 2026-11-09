import pandas as pd
from stock_search import build_catalog, matches
base={'042660.KS':'한화오션','102110.KS':'TIGER 200','042700.KS':'한미반도체'}
batch=pd.DataFrame([{'티커':'086520','종목명':'에코프로비엠','시장':'KOSDAQ'}])
c=build_catalog(base,batch)
assert matches('한화오션',c)[0][0]=='042660.KS'
assert matches('042660',c)[0][0]=='042660.KS'
assert matches('에코프로비엠',c)[0][0]=='086520.KQ'
assert matches('TIGER 200',c)[0][0]=='102110.KS'
assert matches('한미반도체',c)[0][0]=='042700.KS'
print('5 search tests passed')
