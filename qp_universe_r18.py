"""R18 curated-first candidate selection. No claims of verified fundamentals.
Only scanner candidates are affected; historical audit rows remain untouched.
"""
import re
import pandas as pd

# Known inverse / leveraged exchange-traded products (including ambiguous short tickers).
EXCLUDED_TICKERS = set('TQQQ SQQQ UPRO SPXU SPXL SPXS SOXL SOXS TECL TECS FAS FAZ TNA TZA LABU LABD BULZ BERZ UVXY SVXY QLD QID SSO SDS UWM TWM DDM DXD UDOW SDOW ROM REW USD SSG UYG SKF ERX ERY NUGT DUST JNUG JDST TMF TMV TBT TBF PST UBT DRN DRV BOIL KOLD BITX BITU SBIT MSTX MSTU NVDL NVDQ NVDX TSLL TSLQ TSLS CONL CONI FNGU FNGD'.split())
EXCLUDED_TICKERS.update({'114800.KS','122630.KS','252670.KS','252710.KS','233740.KS','251340.KS','261220.KS','261240.KS','123310.KS','123320.KS'})
# Conservative pattern: only used on ETF/ETN names, not ordinary stock names.
LEVERAGE_NAME = re.compile(r'(?i)(레버리지|인버스|곱버스|\b(?:inverse|leveraged|ultrashort|ultra short|ultrapro|ultra pro|daily\s*(?:-?[23]x|[23]x)|[23]x\s*(?:daily|bull|bear|long|short)|-?[23]x|bear\s*[23]x|bull\s*[23]x)\b|(?:2배|3배|마이너스\s*2배))')
# Symbol sets are illustrative stable anchor candidates, not certified value/growth classifications.
QUALITY = '005930.KS 000660.KS 035420.KS 005380.KS 000270.KS 105560.KS 055550.KS 086790.KS 068270.KS 207940.KS 051910.KS 006400.KS 035720.KS 012330.KS 066570.KS 003550.KS 017670.KS 030200.KS 015760.KS 034730.KS AAPL MSFT GOOGL GOOG AMZN META NVDA BRK-B JPM V MA COST UNH JNJ PG KO PEP WMT HD ABBV XOM CVX AVGO ORCL CRM ADBE NFLX AMD TXN QCOM'.split()
GROWTH_WATCH = '042700.KS 247540.KQ 196170.KQ 145020.KQ 039030.KQ 058470.KQ 078600.KQ 036930.KQ 041510.KQ 263750.KQ 112040.KQ 293490.KQ 214150.KQ 403870.KS 373220.KS 329180.KS 009830.KS 267260.KS 010120.KS 298040.KS PLTR CRWD PANW NOW SNOW DDOG NET MDB SHOP UBER ABNB MELI SE APP DUOL HOOD COIN RBLX SOFI RKLB ASTS IONQ HIMS CELH TOST DUOL AXON SMCI ANET VRT'.split()
THEME = '000660.KS 005930.KS 042700.KS 035420.KS 035720.KS 373220.KS 006400.KS 051910.KS 207940.KS 068270.KS 012450.KS 047810.KS 042660.KS 329180.KS 009540.KS 267260.KS 010120.KS 034020.KS 298040.KS 017670.KS NVDA AMD AVGO TSM ASML ARM MU AMAT LRCX KLAC MSFT GOOGL META AMZN TSLA PLTR CRWD PANW SMCI ANET VRT GE VST CEG NEE LLY NVO ISRG'.split()
TARGETS=[('우량주 관찰군',50,QUALITY),('성장·가치 검토군',50,GROWTH_WATCH),('테마 대표 관찰군',50,THEME)]

def eligible(frame):
    if frame.empty: return frame.copy()
    f=frame.copy(); names=f['name'].fillna('').astype(str)
    types=f['asset_type'].fillna('').astype(str).str.upper()
    markets=f['market'].fillna('').astype(str).str.upper()
    etp=types.str.contains('ETF|ETN|ETP',regex=True) | markets.str.contains('ETF|ETN|ETP',regex=True)
    # Some provider catalogs classify ETPs as stocks; known symbols always blocked.
    blocked=f['ticker'].astype(str).str.upper().isin(EXCLUDED_TICKERS) | (etp & names.str.contains(LEVERAGE_NAME,regex=True))
    return f.loc[~blocked].copy().reset_index(drop=True)

def choose(catalog, existing, state, batch_size, rotation_fn, revisit_limit=25):
    """Targets 50+50+50+25+100. Shortfall goes to market-balanced rotation.
    Deduplicates across buckets, never invents financial fundamentals.
    """
    cat=eligible(catalog); n=min(len(cat),max(1,int(batch_size)))
    by_ticker=cat.set_index('ticker',drop=False)
    chosen=[]; seen=set(); counts={}; groups={}
    def add(ticker,group):
        if ticker in seen or ticker not in by_ticker.index or len(chosen)>=n: return False
        chosen.append(by_ticker.loc[ticker]); seen.add(ticker); groups[ticker]=group; return True
    for name,quota,seeds in TARGETS:
        count=0
        for ticker in seeds:
            if count>=quota: break
            if add(ticker,name): count+=1
        counts[name]=count
    # Revisit top scoring candidates with a completed scan at least 24h ago.
    count=0
    if revisit_limit and not existing.empty and {'ticker','score','scanned_at_utc'}.issubset(existing):
        old=existing.copy(); old['score']=pd.to_numeric(old.score,errors='coerce')
        dates=pd.to_datetime(old.scanned_at_utc,utc=True,errors='coerce')
        old=old.loc[dates.lt(pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=1))]
        for t in old.sort_values('score',ascending=False).drop_duplicates('ticker').ticker.astype(str):
            if count>=revisit_limit: break
            if add(t,'기존 우수 후보'): count+=1
    counts['기존 우수 후보']=count
    # Rotate through all eligible markets, then skip already selected symbols.
    # Ask for the full eligible catalog so overlapping anchors do not starve rotation.
    rotated,cursors=rotation_fn(cat,state,min(len(cat),max(n*2,350)))
    rotation_count=0
    for t in rotated.ticker.astype(str):
        if len(chosen)>=n: break
        if add(t,'신규 순환 발굴'): rotation_count+=1
    # Rare collision-heavy batches get an extra rotation pass.
    if len(chosen)<n:
        more,cursors=rotation_fn(cat,{'market_cursors':cursors},min(len(cat),n*2))
        for t in more.ticker.astype(str):
            if len(chosen)>=n: break
            if add(t,'신규 순환 발굴'): rotation_count+=1
    counts['신규 순환 발굴']=rotation_count
    if not chosen: return cat.head(0),cursors,counts
    result=pd.DataFrame(chosen).reset_index(drop=True)
    result['selection_group']=result.ticker.map(groups)
    return result,cursors,counts
