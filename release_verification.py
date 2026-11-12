"""Local release verification. Does not access user accounts or change trading data."""
import ast
import argparse
from pathlib import Path
import sys
import pandas as pd
from statistical_validation import audit, evaluate

def verify(root):
    failures=[]
    for f in ('app.py','simple_dashboard.py','qp_home_r12.py','qp_weekly.py','qp_manual_r15.py','qp_admin_r14.py','recommendation_tracker.py','forward_validation_v95.py','statistical_validation.py','validation_smoke.py'):
        try: ast.parse((root/f).read_text(encoding='utf-8'))
        except Exception as e: failures.append(f'{f}: {e}')
    app=(root/'simple_dashboard.py').read_text(encoding='utf-8')
    for label in ('종목추천순위','관심종목 분석','추천 종목 분석'):
        if label not in app: failures.append(f'UI label missing: {label}')
    home=(root/'qp_home_r12.py').read_text(encoding='utf-8')
    for label in ('오늘수익률','전일수익률','5일수익률','20일수익률','상승 적중률','분석 완료(KST)','#D32F2F','#1565C0'):
        if label not in home: failures.append(f'R12 missing: {label}')
    if 'from qp_home_r12 import show' not in app or 'QP-R15' not in app: failures.append('R12 entrypoint not connected')
    workflow=(root/'.github/workflows/market_scan_v90.yml').read_text()
    for label in ('0 1 * * 1-5','0 6 * * 1-5','python qp_weekly.py'):
        if label not in workflow: failures.append(f'Weekly workflow missing: {label}')
    sample=pd.DataFrame([{'ticker':'AAA','period':'스윙','entry_date':'2026-01-02','entry_close':100,
                          'date_1d':'2026-01-05','close_1d':102,'return_1d_pct':2.0},
                         {'ticker':'BBB','period':'스윙','entry_date':'2026-01-02','entry_close':100,
                          'date_1d':None,'close_1d':None,'return_1d_pct':None}])
    if audit(sample): failures.append(f'Valid data rejected: {audit(sample)}')
    result=evaluate(sample,1)
    if result['observed']!=1 or result['total']!=2 or result['coverage_pct']!=50: failures.append('Coverage calculation failed')
    invalid=sample.copy();invalid.loc[0,'date_1d']='2026-01-02'
    if not audit(invalid):failures.append('Future-date integrity check failed')
    if evaluate(sample,5)['observed']!=0:failures.append('Unmatured observations misreported')
    if failures:
        for issue in failures:print('FAIL:',issue)
        return 1
    print('PASS: Python syntax, menu labels, sample statistics, observation gating and integrity checks')
    data=root/'market_scan_data/recommendation_history.csv'
    if data.exists():
        df=pd.read_csv(data,dtype={'ticker':str}); issues=audit(df)
        for h in (1,5,20):print('HORIZON',h,evaluate(df,h))
        if issues:
            for issue in issues:print('DATA ISSUE:',issue)
            return 1
    else:print('INFO: real recommendation history absent locally; live statistical significance NOT verified')
    return 0

if __name__=='__main__':sys.exit(verify(Path(__file__).resolve().parent))
