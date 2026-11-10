"""Read-only news context; external RSS may be unavailable. No trading score changes."""
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from urllib.request import Request, urlopen
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
