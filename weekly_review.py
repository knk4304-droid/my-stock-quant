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
