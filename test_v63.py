import pandas as pd
from technical_report_v63 import analyze_history
idx=pd.bdate_range('2026-06-01',periods=110)
prices=[100+i*.35 for i in range(110)]
d=pd.DataFrame({'High':[p+2 for p in prices],'Low':[p-2 for p in prices],'Close':prices,'Volume':[1000+i for i in range(110)]},index=idx)
r=analyze_history(d)
assert 0<=r['종합 점수(100)']<=100
assert r['1차 목표 관찰가']<r['2차 목표 관찰가']
assert r['손실 제한 참고가']<r['2차 매수 관찰가']
print('v6.3 기술 지표 기본 테스트 통과')
