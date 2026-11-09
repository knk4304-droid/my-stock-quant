"""Layered symbol lookup. Never invent a quote or score for unresolved symbols."""
import re
import requests

KOREAN = re.compile(r'[가-힣]')
SIX = re.compile(r'^\d{6}$')
SYMBOL = re.compile(r'^[A-Z0-9][A-Z0-9.\-^]{0,24}$')


def _clean(s):
    return re.sub(r'\s+', '', str(s or '')).casefold()


def build_catalog(name_map, batch=None):
    """Use the full scheduled batch catalog as well as the small live sample."""
    catalog = dict(name_map)
    if batch is not None and not batch.empty:
        ticker_col = next((c for c in ('티커','ticker','Ticker','symbol','Symbol') if c in batch.columns), None)
        name_col = next((c for c in ('종목명','name','Name','종목','stock_name') if c in batch.columns), None)
        if ticker_col:
            for _, row in batch.iterrows():
                ticker = str(row[ticker_col]).strip().upper()
                if SIX.fullmatch(ticker):
                    ticker = ticker + ('.KQ' if str(row.get('시장', row.get('Market', ''))).upper().find('KOSDAQ') >= 0 else '.KS')
                if ticker and ticker != 'NAN':
                    name = str(row[name_col]).strip() if name_col else ticker
                    catalog.setdefault(ticker, name if name and name != 'nan' else ticker)
    return catalog


def matches(query, catalog, limit=30):
    q = _clean(query)
    if not q:
        return []
    exact = [(t, n) for t, n in catalog.items() if _clean(n) == q or _clean(t) == q or _clean(t.split('.')[0]) == q]
    partial = [(t, n) for t, n in catalog.items() if q in _clean(n) or q in _clean(t)]
    return (exact + [v for v in partial if v not in exact])[:limit]


def remote_search(query, limit=15):
    """Yahoo public search is best-effort; availability and naming vary by provider."""
    found = []
    try:
        res = requests.get('https://query1.finance.yahoo.com/v1/finance/search',
                           params={'q':query,'quotesCount':limit,'newsCount':0},
                           headers={'User-Agent':'Mozilla/5.0'}, timeout=6)
        res.raise_for_status()
        for item in res.json().get('quotes', []):
            symbol = str(item.get('symbol') or '').upper().strip()
            if not SYMBOL.fullmatch(symbol):
                continue
            name = str(item.get('shortname') or item.get('longname') or symbol)
            found.append((symbol, name))
    except (requests.RequestException, ValueError, TypeError):
        pass
    return found


def krx_search(query, limit=15):
    """Optional comprehensive Korean listing if FinanceDataReader is installed."""
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing('KRX')
        code_col = next((c for c in ('Code','Symbol') if c in listing.columns), None)
        name_col = next((c for c in ('Name','종목명') if c in listing.columns), None)
        market_col = next((c for c in ('Market','시장') if c in listing.columns), None)
        if not code_col or not name_col:
            return []
        results = []
        for _, row in listing.iterrows():
            code = str(row[code_col]).strip().zfill(6)
            name = str(row[name_col]).strip()
            if not SIX.fullmatch(code) or (_clean(query) not in _clean(name) and query != code):
                continue
            market = str(row[market_col]).upper() if market_col else ''
            suffix = '.KQ' if 'KOSDAQ' in market else '.KS'
            results.append((code+suffix, name))
            if len(results) >= limit:
                break
        return results
    except (ImportError, Exception):
        return []


def candidates(query, catalog, include_remote=False):
    query = str(query or '').strip()
    local = matches(query, catalog)
    if not include_remote:
        return local
    remote = krx_search(query) if KOREAN.search(query) or SIX.fullmatch(query) else []
    remote += remote_search(query)
    if SIX.fullmatch(query):
        remote += [(query+'.KS', query+' (코스피 확인)'), (query+'.KQ', query+' (코스닥 확인)')]
    elif SYMBOL.fullmatch(query.upper()) and not KOREAN.search(query):
        remote += [(query.upper(), query.upper())]
    seen = set()
    return [(s,n) for s,n in local+remote if not (s in seen or seen.add(s))][:40]
