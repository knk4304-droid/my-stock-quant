"""Scheduled entry review, not execution signals. Scores are heuristic, unvalidated."""
import math
import pandas as pd
from technical_report_v63 import analyze_history

def evaluate(bars, ticker, period, now):
    d=bars.sort_index().dropna(subset=['Close','High','Low','Volume'])
    if len(d)<66: raise ValueError('insufficient history')
    kr=ticker.endswith(('.KS','.KQ')); zone='Asia/Seoul' if kr else 'America/New_York'
    local=now.tz_convert(zone); date=d.index[-1].date()
    # Exclude incomplete daily candles, including Korean 15:00 and US pre-close.
    if date>=local.date(): d=d[d.index.date<local.date()]
    if len(d)<66: raise ValueError('insufficient completed history')
    r=analyze_history(d,'KRW' if kr else 'USD'); prev=analyze_history(d.iloc[:-1],r['통화'])
    c=float(r['기준 종가']); ma=float(r['5일선'] if period.startswith('단기') else r['20일선']); rsi=float(r['RSI(14)']); hist=float(r['MACD 히스토그램']); old=float(prev['MACD 히스토그램']); vol=float(r['거래량/20일 평균']); atr=float(r['ATR(14)']); support=float(r['최근 20일 지지 후보']); stop=float(r['손실 제한 참고가']); target=float(r['1차 목표 관찰가']); entry=float(r['1차 매수 관찰가']); annual=float(d.Close.pct_change().tail(60).std()*math.sqrt(252)); rr=(target-c)/(c-stop) if 0<stop<c<target else 0
    if not all(math.isfinite(x) for x in (c,ma,rsi,hist,old,vol,atr,support,stop,target,entry,annual,rr)) or min(c,ma,atr)<=0: raise ValueError('invalid indicators')
    gap=(c/ma-1)*100; up=c>=float(d.Close.iloc[-2]); near=0<=gap<= (3 if period.startswith('단기') else 5)
    trend=c>=ma and r['20일선']>=r['60일선']; momentum=hist>0 and hist>old
    score=(25 if trend else 0)+(20 if 45<=rsi<=65 else 10 if 40<=rsi<=70 else 0)+(20 if momentum else 8 if hist>old else 0)+(15 if vol>=1.2 and up else 5 if vol>=.8 and up else 0)+(10 if near else 0)+(10 if rr>=2 else 5 if rr>=1.5 else 0)
    reasons=[]
    if not trend: reasons.append('추세 회복 확인')
    if rsi>70 or gap>8: reasons.append('과열·추격 주의')
    if not momentum: reasons.append('MACD 양수·증가 확인')
    if vol<1.2 or not up: reasons.append('상승 거래량 확인')
    if not near: reasons.append('평균선 부근 지지 확인')
    if rr<2: reasons.append('현재 기준가 손익비 2 미만')
    if annual>.8 or atr/c>.07: reasons.append('높은 변동 위험')
    age=(local.date()-d.index[-1].date()).days
    if age>4: reasons.append('가격 자료 오래됨')
    status='조건부 매수 검토' if score>=80 and not reasons else '조정 대기' if trend and (rsi>70 or gap>8 or not near) else '관망'
    return {'점수':score,'판단':status,'기준일':r['기준일'],'기준가':c,'통화':r['통화'],'RSI':rsi,'MACD':hist,'직전 MACD':old,'거래량 배율':vol,'평균선 이격(%)':round(gap,2),'연율변동성(%)':round(annual*100,2),'ATR':atr,'지지 후보':support,'매수 관찰가':entry,'2차 매수 관찰가':r['2차 매수 관찰가'],'목표가':target,'2차 목표가':r['2차 목표 관찰가'],'손절 참고가':stop,'손익비':round(rr,2),'확인사항':' · '.join(reasons) or '실시간 호가·지지·공시 확인 후 판단'}

def capture(groups, now):
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor
    candidates={}
    for group,rows in groups.items():
        p,m,t=group.split('|')
        if p.startswith(('단기','스윙')) and t=='전체':
            for row in rows: candidates[row['ticker']]=row
    def fetch(t):
        try: return t,yf.Ticker(t).history(period='9mo',interval='1d',auto_adjust=False,timeout=10)
        except Exception: return t,None
    with ThreadPoolExecutor(max_workers=5) as pool: data=dict(pool.map(fetch,candidates))
    reports={}
    for t,bars in data.items():
        if bars is None: continue
        for p in ('단기','스윙'):
            try: reports[(t,p)]=evaluate(bars,t,p,now)
            except Exception: continue
    result={}
    for group,rows in groups.items():
        p,m,theme=group.split('|'); short=p.split()[0]
        if short not in ('단기','스윙'): continue
        out=[]
        for row in rows:
            r=reports.get((row['ticker'],short))
            if r: out.append({'종목':row['name'],'티커':row['ticker'],'기존 순위':row['rank'],**r})
        out.sort(key=lambda r:(r['판단']=='조건부 매수 검토',r['점수']),reverse=True)
        result[group]={'rows':out,'total':len(rows)}
    return result

def show(st, records, group):
    st.subheader('3-1. 업데이트 기준 매수 타이밍 TOP10')
    st.caption('정기 회차의 기존 TOP10 중 상세지표를 확보한 후보를 재정렬합니다. 시장별 전체 테마 TOP10의 합집합만 추가 조회하므로 세부 테마는 일부 누락될 수 있습니다. 확정 일봉 기반이며 실시간 주문 신호가 아닙니다.')
    if not group.startswith(('단기','스윙')): st.info('단기 또는 스윙을 선택하세요.'); return
    if not records: st.info('정기 회차가 아직 없습니다.'); return
    rec=max(records,key=lambda x:x['slot']); st.write('최근 기록: '+rec['slot']+' / 유형: '+rec.get('source','이전 기록')+' / 생성: '+rec['captured'])
    block=rec.get('entry_review',{}).get(group)
    if not block:
        st.info('이 회차에 저장된 매수 타이밍 분석이 없습니다. R19 적용 후 GitHub Actions를 수동 실행하거나 다음 예약 실행을 기다리세요. 기존 회차의 매수 판단을 사후에 만들어 넣지는 않습니다.')
        return
    rows=block['rows']; st.caption(f"상세 분석 성공 {len(rows)}/{block['total']}개 · 누락은 순위 제외 · 장중 일봉 제외")
    if not rows: st.warning('상세 지표를 확보하지 못했습니다.'); return
    if not any(r['판단']=='조건부 매수 검토' for r in rows): st.info('현재 조건부 매수 검토 후보 없음. 무리한 진입을 피하세요.')
    df=pd.DataFrame(rows); df.insert(0,'타이밍 순위',range(1,len(df)+1)); st.dataframe(df[['타이밍 순위','종목','기존 순위','점수','판단','기준일','기준가','통화','RSI','MACD','직전 MACD','거래량 배율','손익비','확인사항']],hide_index=True,use_container_width=True)
    choice=st.selectbox('매수 타이밍 상세 확인',range(len(rows)),format_func=lambda i:rows[i]['종목'],key='qp_entry_choice'); st.table(pd.DataFrame([{'항목':k,'값':v} for k,v in rows[choice].items()]))
    st.caption('점수: 추세 25, RSI 20, MACD 20, 거래량 15, 평균선 근접 10, 손익비 10. 변동성·자료 노후·과열 등 위험 조건은 매수 검토를 제한합니다. 공시·실시간 호가·분봉은 별도 확인하세요.')
