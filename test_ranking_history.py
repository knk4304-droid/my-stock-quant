import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from ranking_history import record_snapshot, PERIODS

class RankingHistoryTests(unittest.TestCase):
    def test_multiple_runs_keep_independent_rankings(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            now = datetime(2026, 11, 11, 5, 0, tzinfo=timezone.utc)
            rows = [dict(ticker='AAA',name='Alpha',score=80,return_5d_pct=2,return_20d_pct=5,volatility_annual=.2,scanned_at_utc=now.isoformat(),market='NASDAQ',asof_price='2026-11-10'),dict(ticker='BBB',name='Beta',score=60,return_5d_pct=1,return_20d_pct=3,volatility_annual=.2,scanned_at_utc=now.isoformat(),market='NASDAQ',asof_price='2026-11-10')]
            pd.DataFrame(rows).to_csv(p/'scores.csv', index=False)
            self.assertTrue(record_snapshot(p, now=now))
            rows[0]['score']=20
            rows[1]['score']=90
            pd.DataFrame(rows).to_csv(p/'scores.csv', index=False)
            self.assertTrue(record_snapshot(p, now=now.replace(hour=6)))
            history=json.loads((p/'ranking_snapshots.json').read_text())
            self.assertEqual(len(history),2)
            self.assertEqual(history[0]['periods'][PERIODS[1]][0]['ticker'],'AAA')
            self.assertEqual(history[1]['periods'][PERIODS[1]][0]['ticker'],'BBB')

if __name__=='__main__': unittest.main()
