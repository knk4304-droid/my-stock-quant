"""Lightweight, deterministic checks for dashboard coverage and recommendation hygiene."""
import pandas as pd


def dashboard_coverage(requested, analyzed, stored=None):
    """Summarize separate live and batch universes without conflating their scores."""
    requested = max(int(requested or 0), 0)
    analyzed = analyzed if isinstance(analyzed, pd.DataFrame) else pd.DataFrame()
    live = set(analyzed['티커'].dropna().astype(str).str.strip()) if '티커' in analyzed else set()
    stored_set = set()
    if isinstance(stored, pd.DataFrame) and not stored.empty:
        for c in ('티커', 'ticker', 'symbol', 'Ticker'):
            if c in stored:
                stored_set = set(stored[c].dropna().astype(str).str.strip()) - {''}
                break
    return {
        'requested': requested, 'live': len(live), 'stored': len(stored_set),
        'overlap': len(live & stored_set),
        'live_pct': round(100 * len(live) / requested, 1) if requested else 0.0,
        'stored_only': len(stored_set - live),
    }


def ranking_safety(frame):
    """Detect empty, non-finite or duplicate entries; does not assess accuracy."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {'rows': 0, 'unique': 0, 'duplicate': 0, 'missing_score': 0}
    ticker = frame['티커'].astype('string').str.strip() if '티커' in frame else pd.Series([''] * len(frame))
    ticker = ticker.fillna('')
    valid = ticker.ne('')
    duplicate = int(ticker[valid].duplicated().sum())
    if '총점' in frame:
        score = pd.to_numeric(frame['총점'], errors='coerce')
        missing_score = int((score.isna() | ~score.between(0, 100)).sum())
    else:
        missing_score = len(frame)
    return {'rows': len(frame), 'unique': int(ticker[valid].nunique()), 'duplicate': duplicate, 'missing_score': missing_score}
