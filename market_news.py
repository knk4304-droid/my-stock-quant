"""Read-only news context; external RSS may be unavailable. No trading score changes."""
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import email.utils
import xml.etree.ElementTree as ET
import re
import html

NEWS_FEED = 'https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko'
MACRO_QUERY = '(증시 OR 코스피 OR 나스닥 OR 연준 OR 금리 OR 환율) when:2d'

def _clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', s or ''))).strip()

def fetch_news(query, limit=6):
    """Return headlines with source/date/link, never infer facts from missing data."""
    url=NEWS_FEED.format(q=quote(query))
    req=Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; StockResearchReader/1.0)'})
    try:
        with urlopen(req, timeout=6) as response:
            data=response.read(350000)
        root=ET.fromstring(data)
    except (OSError, ValueError, ET.ParseError) as exc:
        return [], '뉴스 피드를 읽지 못했습니다. 네트워크 또는 제공처 제한을 확인하세요.'
    result=[]; seen=set()
    for item in root.findall('.//channel/item'):
        title=_clean(item.findtext('title'))
        link=(item.findtext('link') or '').strip()
        if not title or not link or title.casefold() in seen: continue
        seen.add(title.casefold())
        published=(item.findtext('pubDate') or '').strip()
        try:
            dt=email.utils.parsedate_to_datetime(published)
            date=dt.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')
        except (ValueError, TypeError, OverflowError): date='발행 시각 확인 불가'
        source=item.find('source')
        source_name=_clean(source.text if source is not None else '') or '출처 확인 필요'
        result.append({'title':title,'url':link,'date':date,'source':source_name})
        if len(result)>=limit: break
    return result, None

def ticker_query(name, ticker):
    name=(name or '').strip(); ticker=(ticker or '').strip().upper()
    if name and name.lower() != ticker.lower():
        return f'"{name}" (주식 OR 실적 OR 공시 OR 증시) when:7d'
    return f'"{ticker}" (stock OR earnings OR shares) when:7d'

def display_news(st, query, key, limit=5):
    """Show transparent source-linked news; use caller-provided st.cache_data."""
    @st.cache_data(ttl=1800, show_spinner=False)
    def cached(q, n): return fetch_news(q, n)
    articles,error=cached(query,limit)
    if error: st.info(error); return
    if not articles:
        st.info('해당 검색어의 최근 기사를 확인하지 못했습니다. 뉴스가 없다는 의미는 아닙니다.')
        return
    for item in articles:
        st.markdown(f"**[{item['title']}]({item['url']})**")
        st.caption(f"{item['source']} · {item['date']}")
    st.caption('제목과 원문 링크를 제공하는 참고 자료입니다. 기사 내용의 사실관계·기업 영향은 원문과 공식 공시로 확인하세요. 최대 30분간 캐시됩니다.')

def display_company_context(st, name, ticker, key):
    with st.expander('📰 이 종목의 최신 뉴스·중요 공시 확인',expanded=False):
        st.caption('현재 종목과 관련된 최근 뉴스 제목을 확인합니다. 뉴스는 기술점수·매수/목표/손절 가격에 자동 반영되지 않습니다.')
        display_news(st,ticker_query(name,ticker),key)
        st.markdown('[국내 공식 공시 확인 — DART](https://dart.fss.or.kr/) · [미국 공식 공시 확인 — SEC EDGAR](https://www.sec.gov/edgar/search/)')
        st.caption('공시 원문은 공식 사이트에서 종목명 또는 회사명으로 직접 검색하세요. 현재 화면은 공식 공시를 자동 조회·판정하지 않습니다.')

# Briefing layer: title-based signals are explicitly hypotheses, not article-body facts.
from collections import defaultdict

ISSUES = [
 ('시장 급등·급락', ('코스피','코스닥','증시','주가','지수','사이드카','급등','급락'), '시장 전반의 위험 선호와 변동성에 영향을 줄 수 있습니다.', '지수 등락폭·거래대금·외국인 수급을 확인하세요.'),
 ('금리·통화정책', ('금리','연준','fomc','fed','인하','인상','물가'), '할인율 변화로 성장주와 채권·환율에 영향을 줄 수 있습니다.', '발표 수치와 시장 예상치의 차이를 확인하세요.'),
 ('환율·해외시장', ('환율','달러','원화','나스닥','미국 증시','뉴욕증시'), '수출 기업 실적 기대와 외국인 자금 흐름에 영향을 줄 수 있습니다.', '달러·원 환율과 미국 지수 선물 움직임을 확인하세요.'),
 ('기업 실적·산업', ('실적','영업이익','반도체','hbm','ai','수주','계약','배당'), '해당 업종의 이익 전망과 투자심리를 바꿀 수 있습니다.', '실제 공시·실적과 시장 기대치의 차이를 확인하세요.'),
 ('기업 자금·지배구조', ('유상증자','전환사채','자사주','합병','인수','감자','거래정지'), '주식 수 변화·재무 건전성·지배구조 위험을 점검할 필요가 있습니다.', '공시 원문과 자금 사용 목적을 확인하세요.'),
]

def _headline_core(title):
    return re.sub(r'\s*[-–|]\s*[^-–|]+$', '', title or '').strip()


def _headline_tokens(title):
    # Similar titles from syndicated outlets should not count as independent events.
    stop={'오늘','증시','주식','시장','관련','속보','뉴스','기자','대한','이후','이번','국내','미국','기업'}
    return {x for x in re.findall(r'[가-힣]{2,}|[a-zA-Z]{3,}|\d+(?:\.\d+)?%', _headline_core(title).lower()) if x not in stop}


def group_headlines(articles, max_groups=5):
    """Group topic and near-duplicate headlines without claiming article-body verification."""
    groups=defaultdict(list)
    tokens_seen=[]
    for article in articles:
        title=article.get('title','')
        tokens=_headline_tokens(title)
        if not tokens: continue
        duplicate=any(len(tokens & prev)/max(1,min(len(tokens),len(prev)))>=0.78 and len(tokens & prev)>=3 for prev in tokens_seen)
        if duplicate: continue
        tokens_seen.append(tokens)
        low=title.lower()
        matched=next((name for name,terms,*_ in ISSUES if any(term in low for term in terms)), '기타 종목·시장 소식')
        groups[matched].append(article)
    return sorted(groups.items(),key=lambda x:-len(x[1]))[:max_groups]

BRIEF_GUIDE = {
 '시장 급등·급락': ('단기에는 지수 급등락과 함께 개별 종목의 변동성이 커질 수 있습니다. 상승 뉴스라도 거래량이 약하거나 일부 대형주에만 매수가 집중되면 상승세가 지속되지 않을 수 있습니다.', '중기에는 기업 실적과 경기 전망이 실제로 개선되는지가 중요합니다. 지수 반등이 기업 이익 개선 없이 진행되면 되돌림 위험이 있습니다.', '코스피·코스닥의 상승 종목 수, 거래대금, 외국인·기관 수급을 함께 확인하세요. 지수는 오르는데 보유 종목이 하락한다면 업종별 차이를 점검하세요.'),
 '금리·통화정책': ('예상보다 완화적인 금리 신호는 성장주에 유리할 수 있지만, 물가 재상승 우려가 커지면 반대로 작용할 수 있습니다. 금리 결정 자체보다 시장 예상과의 차이가 중요합니다.', '중기에는 기업의 자금조달 비용, 소비·투자, 채권금리 추세가 실제 이익 전망에 반영되는지 확인해야 합니다.', '기준금리뿐 아니라 국채금리, 물가 지표, 연준 발언, 시장의 금리 전망 변화를 확인하세요. 발표 직후 급등락만으로 추격 매수하지 마세요.'),
 '환율·해외시장': ('원화 약세는 일부 수출기업의 원화 환산 실적에 도움이 될 수 있으나 원자재 수입기업에는 부담이 될 수 있습니다. 미국 기술주 하락은 국내 반도체 투자심리에 영향을 줄 수 있습니다.', '중기에는 환율이 지속되는 이유와 실제 수출 단가·물량, 외국인 수급을 살펴야 합니다.', '원·달러 환율, 미국 주요 지수, 업종별 해외 매출 비중과 환헤지 여부를 확인하세요. 환율 변화만으로 모든 수출주에 같은 판단을 적용하지 마세요.'),
 '기업 실적·산업': ('실적 호조나 수주 뉴스는 해당 기업의 기대 이익을 높일 수 있습니다. 그러나 이미 주가에 반영되었거나 기대에 못 미치면 좋은 뉴스에도 하락할 수 있습니다.', '중기에는 매출보다 영업이익률, 현금흐름, 신규 수주의 실제 매출 전환 여부가 중요합니다.', '공식 공시에서 실적의 전년 동기 대비 변화, 시장 예상치와의 차이, 계약 규모·기간·취소 조건을 확인하세요. 동종 업계와 비교해 일회성 효과인지 구분하세요.'),
 '기업 자금·지배구조': ('증자·전환사채는 자금 조달에 도움이 될 수 있지만 주식 수 증가에 따른 희석 우려가 있습니다. 자사주 매입·소각은 주주환원 기대를 높일 수 있으나 실행 여부가 중요합니다.', '중기에는 조달한 자금의 사용 성과, 재무 건전성, 실제 발행·소각 규모에 따라 영향이 달라집니다.', '공시의 발행 규모, 발행가, 전환 가능 시점, 자금 사용 목적, 최대주주 변경 여부를 확인하세요. 제목만 보고 호재·악재를 단정하지 마세요.'),
}

def display_briefing(st, query, key, limit=25, company=False):
    @st.cache_data(ttl=1800,show_spinner=False)
    def cached(q,n): return fetch_news(q,n)
    articles,error=cached(query,limit)
    if error:
        st.info(error); return
    if not articles:
        st.info('확인된 최근 기사가 없습니다. 관련 사건이 없다는 뜻은 아닙니다.'); return
    groups=group_headlines(articles)
    st.caption(f'수집 기사 {len(articles)}건을 유사 주제별로 정리했습니다. 기사 제목만으로 판단한 잠정 해석이며, 본문·공식 공시 검증 전입니다. 약 30분 동안 갱신되지 않을 수 있습니다.')
    for name,items in groups:
        definition=next((entry for entry in ISSUES if entry[0]==name),None)
        short_impact=definition[2] if definition else '기업과 업종별로 영향이 달라 추가 확인이 필요합니다.'
        short_check=definition[3] if definition else '원문과 공식 발표 자료를 확인하세요.'
        short_core=' / '.join(_headline_core(a['title'])[:90] for a in items[:2])
        st.subheader(name)
        st.caption(f'서로 다른 기사 {len(items)}건 · 아래 내용은 확정된 투자 신호가 아닙니다.')
        st.write('핵심 내용 (제목 기준)')
        st.write(short_core)
        guide=BRIEF_GUIDE.get(name)
        st.write('예상 영향 — 단기')
        st.write(guide[0] if guide else short_impact + ' 실제 기업별 영향은 확인된 자료가 부족해 판단을 보류합니다.')
        st.write('예상 영향 — 중기 및 반대 시나리오')
        st.write(guide[1] if guide else '향후 실적·정책·수급으로 영향이 확인되는지 관찰해야 합니다. 초기 시장 반응과 실제 결과가 달라질 수 있습니다.')
        st.write('투자 시 확인할 점')
        st.write(guide[2] if guide else short_check + ' 발표 날짜와 공식 자료, 가격·거래량 반응을 함께 살펴보세요.')
        st.caption('판단 기준: 공식 사실 확인 → 예상과 실제의 차이 → 가격·거래량 반응 → 보유 기간과 손절 기준 검토')
        with st.expander(f'근거 기사 보기 ({len(items)}건)'):
            for a in items[:6]:
                st.markdown(f"[{a['title']}]({a['url']})")
                st.caption(f"{a['source']} · {a['date']}")
        st.divider()
    st.caption('뉴스 분석은 참고용이며 추천점수·매수가·목표가·손절가에 자동 반영되지 않습니다.')

def _dart_recent(st, ticker):
    """Return verified OpenDART filing summaries for Korean tickers when configured."""
    if not (ticker.endswith('.KS') or ticker.endswith('.KQ')): return None, '미국 공시 자동 조회는 현재 지원하지 않습니다.'
    try: api_key=st.secrets.get('DART_API_KEY','')
    except Exception: api_key=''
    if not api_key: return None, '공식 공시 자동 조회가 설정되지 않았습니다(DART_API_KEY 필요).'
    import io,zipfile,json
    from datetime import date
    @st.cache_data(ttl=86400,show_spinner=False)
    def corp_map(key):
        req=Request('https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key='+quote(key),headers={'User-Agent':'AIStockMaster/1.0'})
        with urlopen(req,timeout=12) as r: blob=r.read(16000000)
        with zipfile.ZipFile(io.BytesIO(blob)) as z: root=ET.fromstring(z.read('CORPCODE.xml'))
        return {e.findtext('stock_code','').strip():e.findtext('corp_code','').strip() for e in root.findall('list') if e.findtext('stock_code','').strip()}
    @st.cache_data(ttl=3600,show_spinner=False)
    def recent(key,code):
        today=datetime.now(timezone(timedelta(hours=9))).date(); start=(today-timedelta(days=45)).strftime('%Y%m%d')
        url=f'https://opendart.fss.or.kr/api/list.json?crtfc_key={quote(key)}&corp_code={code}&bgn_de={start}&end_de={today:%Y%m%d}&page_count=50'
        with urlopen(Request(url,headers={'User-Agent':'AIStockMaster/1.0'}),timeout=10) as r: return json.loads(r.read(400000))
    try:
        code=corp_map(api_key).get(ticker.split('.')[0]);
        if not code: return None,'종목에 대응하는 DART 기업코드를 찾지 못했습니다.'
        result=recent(api_key,code)
        if result.get('status')=='013': return [],None
        if result.get('status')!='000': return None,'공식 공시 조회에 실패했습니다.'
        rows=result.get('list',[])
        priorities=('영업(잠정)실적','매출액또는손익구조','단일판매','공급계약','유상증자','무상증자','전환사채','자기주식','감사의견','최대주주','합병','영업정지','소송','주요사항보고서')
        selected=[r for r in rows if any(p in r.get('report_nm','') for p in priorities)][:3]
        return selected,None
    except (OSError,ValueError,KeyError,ET.ParseError,zipfile.BadZipFile):
        return None,'공시 데이터 제공처 연결에 실패했습니다.'


# OpenDART document.xml is a ZIP containing the original filing text.
# We quote short, source-grounded passages rather than inventing a numeric summary.
FILING_KEYWORDS = (
    '계약금액', '계약상대방', '계약기간', '매출액 대비', '매출액대비',
    '영업이익', '당기순이익', '매출액', '증자금액', '발행주식',
    '발행가액', '신주발행', '자금조달', '취득금액', '처분금액',
    '감사의견', '거래정지', '합병비율', '소송금액', '자기주식',
)


def _extract_filing_passages(raw, limit=3):
    """Short excerpts from actual filing document, never inferred facts."""
    import html as html_lib
    raw = re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1>', ' ', raw)
    raw = re.sub(r'(?i)</(?:tr|p|div|table|section|title|td|th)>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]*>', ' ', raw)
    raw = html_lib.unescape(raw)
    passages=[]; seen=set()
    for line in raw.splitlines():
        line=re.sub(r'\s+', ' ', line).strip()
        if not (12 <= len(line) <= 600): continue
        if not any(k in line for k in FILING_KEYWORDS): continue
        # Prevent header-only matches and table-of-contents from being called facts.
        if not (re.search(r'\d', line) or ('감사의견' in line and len(line)>25)): continue
        norm=re.sub(r'\s+', '', line[:140])
        if norm in seen: continue
        seen.add(norm)
        passages.append(line[:210] + ('…' if len(line)>210 else ''))
        if len(passages)>=limit: break
    return passages


def _parse_dart_document_zip(blob):
    import io,zipfile
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names=[n for n in archive.namelist() if n.lower().endswith(('.xml','.html','.htm'))]
        if not names: return []
        # Guard against large compressed documents and binary payloads.
        texts=[]
        for name in names[:6]:
            if archive.getinfo(name).file_size > 4_000_000: continue
            data=archive.read(name)
            try: decoded=data.decode('utf-8')
            except UnicodeDecodeError: decoded=data.decode('euc-kr',errors='replace')
            texts.append(decoded)
        return _extract_filing_passages('\n'.join(texts))


def _dart_document_passages(st, rcept_no):
    """Retrieve actual DART document; no summary if content cannot be verified."""
    try: api_key=st.secrets.get('DART_API_KEY','')
    except Exception: api_key=''
    if not api_key or not re.fullmatch(r'\d{14}',str(rcept_no or '')):
        return [],'공시 본문을 확인할 수 없습니다.'
    @st.cache_data(ttl=21600,show_spinner=False)
    def load(key,receipt):
        url='https://opendart.fss.or.kr/api/document.xml?crtfc_key='+quote(key)+'&rcept_no='+receipt
        with urlopen(Request(url,headers={'User-Agent':'AIStockMaster/1.0'}),timeout=12) as resp:
            data=resp.read(8_000_000)
        if not data.startswith(b'PK'):
            return [],'공시 원문 API가 문서를 제공하지 않았습니다.'
        return _parse_dart_document_zip(data),None
    try: return load(api_key,str(rcept_no))
    except Exception: return [],'공시 원문 연결 또는 문서 해석에 실패했습니다.'


def _filing_impact_hint(report_name):
    """Conditional watchpoints, not asserted price forecasts."""
    title=(report_name or '').replace(' ','')
    if '유상증자' in title or '전환사채' in title:
        return '확인할 영향: 발행 규모·조건과 기존 주주 지분 희석 가능성. 호재·악재 단정 불가.'
    if '공급계약' in title or '단일판매' in title:
        return '확인할 영향: 계약금액의 매출 대비 비중, 계약기간 및 실제 이익 기여 가능성.'
    if '실적' in title or '손익구조' in title:
        return '확인할 영향: 전년 대비 실적 변화와 시장 예상치 차이. 실적 개선만으로 주가 상승을 단정할 수 없음.'
    if '자기주식' in title:
        return '확인할 영향: 취득·처분 목적, 규모, 일정 및 주주가치 변화 가능성.'
    if '감사의견' in title or '영업정지' in title:
        return '확인할 영향: 재무·상장 관련 위험과 거래 제한 가능성을 우선 점검.'
    return '확인할 영향: 재무구조·실적·주식 수 변화 여부를 원문과 함께 점검.'


SEC_MATERIAL_FORMS = {'8-K','10-Q','10-K','6-K','20-F','S-3','424B5','DEF 14A'}

def _sec_recent(st, ticker):
    """SEC official submission metadata only. No claims about filing body or market direction."""
    symbol=(ticker or '').upper().strip()
    if symbol.endswith(('.KS','.KQ')): return None, None
    if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,12}',symbol):
        return None,'미국 종목코드를 정확하게 입력해야 SEC 공시를 조회할 수 있습니다.'
    try: agent=str(st.secrets.get('SEC_USER_AGENT','')).strip()
    except Exception: agent=''
    if not agent or '@' not in agent:
        return None,'SEC 공식 조회를 사용하려면 Secrets에 SEC_USER_AGENT를 등록하세요. 예: AIStockMaster contact@example.com (본인이 관리하는 연락처 사용)'
    @st.cache_data(ttl=86400,show_spinner=False)
    def tickers(ua):
        req=Request('https://www.sec.gov/files/company_tickers.json',headers={'User-Agent':ua,'Accept-Encoding':'identity'})
        with urlopen(req,timeout=12) as r:
            import json
            return json.loads(r.read(3_000_000))
    @st.cache_data(ttl=3600,show_spinner=False)
    def submissions(ua,cik):
        import json
        req=Request(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',headers={'User-Agent':ua,'Accept-Encoding':'identity'})
        with urlopen(req,timeout=12) as r: return json.loads(r.read(3_000_000))
    try:
        mapping=tickers(agent)
        match=next((v for v in mapping.values() if str(v.get('ticker','')).upper()==symbol.replace('.','-')),None)
        if not match: return None,'SEC 등록 종목코드를 찾지 못했습니다. 상장지와 종목코드를 확인하세요.'
        cik=int(match['cik_str']); obj=submissions(agent,cik)
        rec=obj.get('filings',{}).get('recent',{})
        forms=rec.get('form',[]); dates=rec.get('filingDate',[]); acc=rec.get('accessionNumber',[]); docs=rec.get('primaryDocument',[])
        today=datetime.now(timezone.utc).date(); out=[]
        for form,date,accession,doc in zip(forms,dates,acc,docs):
            try: age=(today-datetime.strptime(date,'%Y-%m-%d').date()).days
            except ValueError: continue
            if age<0 or age>90: continue
            if form not in SEC_MATERIAL_FORMS: continue
            accession_clean=accession.replace('-','')
            out.append({'form':form,'date':date,'url':f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{quote(doc)}'})
            if len(out)>=3: break
        return out,None
    except HTTPError as exc:
        if exc.code in (403,429):
            return None, f'SEC 요청 제한(HTTP {exc.code})입니다. User-Agent 연락처, 호출 빈도, SEC 서버 접근 정책을 확인하고 잠시 후 다시 시도하세요.'
        return None, f'SEC 서버 응답 오류(HTTP {exc.code})입니다. 잠시 후 다시 시도하세요.'
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return None, f'SEC 연결 또는 응답 해석에 실패했습니다({type(exc).__name__}). 잠시 후 다시 확인하세요.'


def _sec_companyfacts(st, ticker):
    """Verified US-GAAP figures from SEC XBRL companyfacts; no estimated values."""
    symbol=(ticker or '').upper().strip()
    try: agent=str(st.secrets.get('SEC_USER_AGENT','')).strip()
    except Exception: agent=''
    if '@' not in agent: return [], 'SEC_USER_AGENT 설정이 필요합니다.'
    @st.cache_data(ttl=86400, show_spinner=False)
    def lookup(ua):
        import json
        req=Request('https://www.sec.gov/files/company_tickers.json',headers={'User-Agent':ua,'Accept':'application/json','Accept-Encoding':'identity'})
        with urlopen(req,timeout=15) as r: return json.loads(r.read(3_000_000))
    @st.cache_data(ttl=21600, show_spinner=False)
    def facts(ua,cik):
        import json
        req=Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',headers={'User-Agent':ua,'Accept':'application/json','Accept-Encoding':'identity'})
        with urlopen(req,timeout=15) as r: return json.loads(r.read(10_000_000))
    try:
        company=next((v for v in lookup(agent).values() if str(v.get('ticker','')).upper()==symbol.replace('.','-')),None)
        if not company: return [], 'SEC에서 종목코드에 대응하는 기업을 찾지 못했습니다.'
        data=facts(agent,int(company['cik_str']))
        usgaap=data.get('facts',{}).get('us-gaap',{})
        fields=[('매출액','RevenueFromContractWithCustomerExcludingAssessedTax'),('매출액','Revenues'),('순이익','NetIncomeLoss'),('영업현금흐름','NetCashProvidedByUsedInOperatingActivities')]
        result=[]; used=set()
        for label,tag in fields:
            if label in used: continue
            units=usgaap.get(tag,{}).get('units',{}).get('USD',[])
            # Only audited/reported filings, not projections. Avoid mixed-duration frames.
            valid=[]
            for item in units:
                if item.get('form') not in ('10-Q','10-K') or item.get('val') is None: continue
                if item.get('fp') not in ('Q1','Q2','Q3','FY'): continue
                if not (item.get('start') and item.get('end') and item.get('filed')): continue
                try:
                    duration=(datetime.fromisoformat(item['end'])-datetime.fromisoformat(item['start'])).days
                except ValueError: continue
                if not 65 <= duration <= 105 and not 330 <= duration <= 380: continue
                valid.append({**item,'duration':duration})
            if not valid: continue
            valid.sort(key=lambda x:(x['end'],x['filed']),reverse=True)
            newest=valid[0]
            # Latest filing may restate old periods; only show latest reported period.
            result.append({'label':label,'value':newest['val'],'end':newest['end'],'start':newest['start'],'filed':newest['filed'],'form':newest['form'],'duration':newest['duration']})
            used.add(label)
        return result,None
    except HTTPError as exc:
        return [], f'SEC 재무 데이터 요청 제한 또는 오류(HTTP {exc.code}). 설정·호출 빈도를 확인하세요.'
    except (OSError,ValueError,TypeError,KeyError) as exc:
        return [], f'SEC 재무 데이터를 확인하지 못했습니다({type(exc).__name__}).'


def _format_usd_amount(value):
    n=value/1_000_000_000
    return f'{n:,.2f}십억 달러' if abs(n)>=1 else f'{value/1_000_000:,.1f}백만 달러'


def _sec_form_explanation(form):
    return {
      '8-K':'미국 기업이 주요 사건을 수시로 보고하는 공시입니다. 구체적 내용과 영향은 원문 확인이 필요합니다.',
      '6-K':'미국에 상장된 해외 기업의 수시 보고 자료입니다. 원문 내용 확인이 필요합니다.',
      '10-Q':'분기 실적·재무상태를 보고하는 문서입니다. 매출·이익·현금흐름과 전분기 비교가 중요합니다.',
      '10-K':'연간 사업·실적·위험 요인을 종합 보고하는 문서입니다.',
      '20-F':'미국에 상장된 해외 기업의 연간 보고서입니다.',
      'S-3':'증권 발행 등록 관련 문서입니다. 실제 발행 여부·규모는 추가 확인이 필요합니다.',
      '424B5':'증권 발행 조건 관련 투자설명서입니다. 발행 규모·가격을 확인하세요.',
      'DEF 14A':'주주총회 의결 안건과 경영진 보수 등 관련 문서입니다.'
    }.get(form,'공식 문서의 세부 내용은 원문 확인이 필요합니다.')

def display_company_brief(st,name,ticker,key):
    with st.expander('📰 최근 이슈 · 중요 공시 요약',expanded=False):
        is_korean=(ticker or '').upper().endswith(('.KS','.KQ'))
        filings,error=_dart_recent(st,ticker) if is_korean else (None,None)
        st.markdown('**국내 공식 중요 공시 (최근 45일)**' if is_korean else '**미국 SEC 공식 공시 (최근 90일)**')
        if not is_korean:
            sec_rows,sec_error=_sec_recent(st,ticker)
            if sec_error: st.info(sec_error)
            elif not sec_rows: st.info('선택 기간에 조회된 주요 SEC 서식이 없습니다. 공시가 전혀 없다는 뜻은 아닙니다.')
            else:
                for item in sec_rows:
                    st.markdown(f"**{item['form']}** · 제출일 {item['date']}")
                    st.write('**서식의 의미:** '+_sec_form_explanation(item['form']))
                    st.caption('SEC에서 확인한 것은 서식 종류와 제출일입니다. 원문 본문 요약이나 호재·악재 판정이 아닙니다.')
                    st.markdown(f"[SEC 공식 제출문서 확인]({item['url']})")
            st.markdown('**SEC 보고 재무 수치 (확인 가능한 경우)**')
            with st.expander('📊 공식 재무 수치 확인 · 기간과 단위 포함', expanded=False):
                figures,fig_error=_sec_companyfacts(st,ticker)
                if fig_error: st.info(fig_error)
                elif not figures: st.info('SEC에서 비교 가능한 주요 재무 항목을 확인하지 못했습니다. 해당 기업의 회계 분류·보고 형식에 따라 값이 없을 수 있습니다.')
                else:
                    for f in figures:
                        term='약 3개월' if f['duration']<110 else '약 1년'
                        st.markdown(f"**{f['label']}**: {_format_usd_amount(f['value'])} · {term} ({f['start']}~{f['end']})")
                        st.caption(f"SEC {f['form']} 보고 · 제출일 {f['filed']} · USD 기준")
                    st.caption('위 수치는 SEC XBRL 보고값입니다. 항목별 최신 보고기간이 다를 수 있으며, 전년 동기 비교·주가 영향은 자동 판정하지 않습니다. 마이너스 값은 손실 또는 순유출을 뜻할 수 있습니다.')
            st.markdown('**관련 뉴스 핵심 흐름**')
            display_briefing(st,ticker_query(name,ticker),key,limit=12,company=True)
            st.caption('SEC·뉴스 정보는 기존 기술점수와 매수·목표·손절 가격에 자동 반영되지 않습니다.')
            return
        if error: st.info(error)
        elif not filings: st.info('설정된 기간에 주요 유형 공시가 조회되지 않았습니다. 모든 공시가 없다는 의미는 아닙니다.')
        else:
            for row in filings:
                label=row.get('report_nm','공시 제목 확인 필요')
                day=row.get('rcept_dt','')
                receipt=str(row.get('rcept_no',''))
                st.markdown(f"**{label}** · {day[:4]}-{day[4:6]}-{day[6:]}" )
                if '정정' in label: st.warning('정정 공시입니다. 이전 공시와 변경된 항목을 원문에서 비교하세요.')
                passages,document_error=_dart_document_passages(st,receipt)
                if passages:
                    st.caption('공식 공시 원문에서 확인한 주요 문장 (자동 발췌 · 최대 3줄)')
                    for passage in passages: st.write('• '+passage)
                else:
                    st.info('공시 제목은 확인됐으나 핵심 본문은 확인하지 못했습니다. 숫자나 내용을 추측하지 않습니다.')
                st.caption(_filing_impact_hint(label))
                if receipt and re.fullmatch(r'\d{14}',receipt):
                    st.markdown(f'[이 공시의 공식 원문 확인](https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt})')
                if document_error: st.caption(document_error)
        st.caption('표시된 공시 제목과 원문 발췌는 동일한 공시 접수번호를 기준으로 합니다. 본문 문장은 자동 발췌이므로 표의 항목·단위·정정공시 여부를 원문에서 확인해야 합니다. 미국 기업의 공시 자동 요약은 아직 지원하지 않습니다.')
        st.markdown('**관련 뉴스 핵심 흐름**')
        display_briefing(st,ticker_query(name,ticker),key,limit=12,company=True)
        st.caption('확인하지 않은 공시 내용을 사실처럼 생성하지 않습니다. 뉴스와 공시 정보는 기존 기술점수에 반영되지 않습니다.')
