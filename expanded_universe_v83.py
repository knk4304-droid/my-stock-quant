"""User-triggered, incremental stock/ETF analysis universe expansion."""
import re
import pandas as pd

TICKER_RE = re.compile(r'^[A-Z0-9][A-Z0-9.\-^]{0,19}$')

def normalize_catalog(stored, extra=None):
    frames = []
    for source in (stored, extra):
        if source is None or not isinstance(source, pd.DataFrame) or source.empty:
            continue
        cols = {str(c).strip().lower(): c for c in source.columns}
        ticker_col = next((cols[k] for k in ('티커','ticker','symbol','종목코드') if k in cols), None)
        if ticker_col is None:
            continue
        name_col = next((cols[k] for k in ('종목명','name','종목이름') if k in cols), None)
        market_col = next((cols[k] for k in ('시장','market','구분') if k in cols), None)
        out = pd.DataFrame({'티커':source[ticker_col].astype('string').str.strip().str.upper()})
        out['종목명'] = source[name_col].astype('string').fillna(out['티커']) if name_col else out['티커']
        out['시장'] = source[market_col].astype('string').fillna('미분류') if market_col else '미분류'
        out = out.loc[out['티커'].notna() & out['티커'].map(lambda t: bool(TICKER_RE.fullmatch(str(t))))].copy()
        frames.append(out)
    if not frames:
        return pd.DataFrame(columns=['티커','종목명','시장'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('티커', keep='last').reset_index(drop=True)

def pending_catalog(catalog, existing_tickers, completed_tickers):
    excluded = set(existing_tickers) | set(completed_tickers)
    return catalog.loc[~catalog['티커'].isin(excluded)].reset_index(drop=True)

def merge_analysis(base, additional):
    if additional is None or additional.empty:
        return base.copy()
    if base is None or base.empty:
        return additional.drop_duplicates('티커', keep='first').reset_index(drop=True)
    return pd.concat([base,additional],ignore_index=True).drop_duplicates('티커',keep='first').reset_index(drop=True)
