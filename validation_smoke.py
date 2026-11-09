"""Offline smoke check for deployed repository data. No network or credentials required."""
import argparse, ast, json, pathlib, sys
from statistical_validation import report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',default='market_scan_data/recommendation_history.csv')
    args=parser.parse_args()
    for name in ('simple_dashboard.py','recommendation_tracker.py','forward_validation_v95.py','statistical_validation.py'):
        ast.parse(pathlib.Path(name).read_text(encoding='utf-8'))
    results=report(args.data)
    print(json.dumps(results,ensure_ascii=False,indent=2))
    if results['issues']:
        print('FAIL: data integrity issues',file=sys.stderr);return 1
    print('PASS: syntax and available recommendation data checks')
    return 0
if __name__=='__main__':sys.exit(main())
