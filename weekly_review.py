"""Weekly decision-support helpers. No unverified headline-based trading scores."""
import io
import math
import pandas as pd

ISSUE_RULES = (
    ('자금조달·희석 점검', ('유상증자', '전환사채', 'cb 발행', '신주발행', '감자', 'dilution', 'offering')),
    ('실적·가이던스 점검', ('실적', '영업이익', '매출', '어닝', 'earnings', 'guidance', 'revenue')),
    ('계약·사업 점검', ('수주', '공급계약', '계약체결', '인수', '합병', 'contract', 'acquisition')),
    ('규제·소송 점검', ('소송', '조사', '제재', '리콜', 'lawsuit', 'investigation', 'recall')),
    ('주주환원 점검', ('배당', '자사주', '소각', 'dividend', 'buyback')),
)

def issue_flags(articles):
    """Headline-only review prompts, never validated positive/negative labels."""
    found = []
    for item in articles:
        title = str(item.get('title', ''))
        low = title.casefold()
        categories = [name for name, words in ISSUE_RULES if any(w in low for w in words)]
        if categories:
            found.append({'분류': ', '.join(categories), '기사 제목': title, '발행 시각': item.get('date','확인 불가'), '출처': item.get('source',''), '원문': item.get('url','')})
    return found

def allocate_krw(selected, budget=10_000_000, risk_per_trade=100_000, daily_risk=300_000):
    """Integer-share hypothetical sizing, conservative against a per-trade risk cap."""
    rows = []
    planned = 0.0
    for r in selected:
        ticker = str(r.get('코드',''))
        buy, stop = float(r['1차 매수가']), float(r['손절 기준가'])
        if not ticker.upper().endswith(('.KS','.KQ')) or buy <= stop or stop <= 0:
            rows.append({'종목':r['종목명'], '코드':ticker, '예시 수량':None, '예시 투자액':None, '손절 시 계획손실':None, '상태':'미국 종목/가격조건: 환율 및 주문단위 확인 필요'})
            continue
        remaining = max(0, daily_risk - planned)
        cap = min(risk_per_trade, remaining)
        qty = max(0, math.floor(min(budget / max(1,len(selected)) / buy, cap / (buy-stop))))
        loss = qty * (buy-stop)
        planned += loss
        rows.append({'종목':r['종목명'], '코드':ticker, '예시 수량':qty, '예시 투자액':round(qty*buy), '손절 시 계획손실':round(loss), '상태':'예시 계산 / 주문 아님'})
    return rows

def csv_bytes(rows):
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig')

# Distinct headlines from syndicated outlets are not independent evidence.
import re
from urllib.parse import urlparse

def _normalized_headline(title):
    title = re.sub(r'\[[^\]]{1,30}\]|\([^)]{1,30}\)', ' ', str(title))
    title = re.sub(r'[^0-9a-z가-힣]+', ' ', title.casefold())
    return ' '.join(title.split())

def deduplicate_articles(articles):
    """Conservative exact normalized-title and exact URL deduplication."""
    seen_titles, seen_urls, output = set(), set(), []
    for item in articles or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        url = str(item.get('url') or '').strip()
        key = _normalized_headline(title)
        if not key or key in seen_titles or (url and url in seen_urls):
            continue
        seen_titles.add(key)
        if url:
            seen_urls.add(url)
        output.append(item)
    return output

ISSUE_CHECKS = {
    '자금조달·희석 점검': '발행 규모, 기존 주식 대비 희석률, 발행가와 자금 사용 목적을 공식 공시로 확인하세요.',
    '실적·가이던스 점검': '매출·영업이익의 전년 동기 대비 증감, 시장 예상치, 다음 분기 전망을 비교하세요.',
    '계약·사업 점검': '계약 금액이 연매출에서 차지하는 비중, 실제 매출 인식 시점, 해지 조건을 확인하세요.',
    '규제·소송 점검': '소송·규제의 진행 단계, 잠재 비용, 사업 중단 가능성을 공식 자료로 확인하세요.',
    '주주환원 점검': '배당 기준일·배당 재원·자사주 소각 여부와 일회성 발표인지 확인하세요.',
}

def summarize_issue_checks(articles, max_items=3):
    """Return non-directional due-diligence prompts, not sentiment or verified news."""
    unique = deduplicate_articles(articles)
    flags = issue_flags(unique)
    groups = {}
    for flag in flags:
        for category in flag['분류'].split(', '):
            group = groups.setdefault(category, {'count': 0, 'example': flag})
            group['count'] += 1
    result = []
    for category, info in sorted(groups.items(), key=lambda pair: (-pair[1]['count'], pair[0]))[:max_items]:
        result.append({
            'category': category,
            'count': info['count'],
            'check': ISSUE_CHECKS.get(category, '원문과 날짜를 확인하세요.'),
            'source_title': info['example']['기사 제목'],
            'source_url': info['example']['원문'],
            'source_date': info['example']['발행 시각'],
        })
    return {'raw_count': len(articles or []), 'unique_count': len(unique), 'checks': result,
            'status': '기사 제목만 확인 / 공시 원문 검증 전'}
