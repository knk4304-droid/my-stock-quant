"""Unified recommendation home. Existing scan and watchlist engines remain untouched."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
from market_news import fetch_news, MACRO_QUERY, ticker_query
from technical_report_v63 import get_technical_report

DATA = Path(__file__).resolve().parent / 'market_scan_data'
INDEXES = {'코스피':'^KS11','코스닥':'^KQ11','S&P 500':'^GSPC','나스닥':'^IXIC'}


def rank_history(ticker, period):
    path = DATA / 'ranking_snapshots.json'
    if not path.exists(): return pd.DataFrame()
    try: snapshots=json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return pd.DataFrame()
    records=[]
    for snap in snapshots:
        rows=snap.get('periods',{}).get(period,[])
        match=next((r for r in rows if str(r.get('ticker'))==str(ticker)),None)
        if match:
            at=pd.to_datetime(snap.get('at_utc'),utc=True,errors='coerce')
            if pd.notna(at): records.append({'검색 시각':at.tz_convert('Asia/Seoul'),'순위':match.get('rank'),'추천점수':match.get('score')})
    return pd.DataFrame(records).sort_values('검색 시각') if records else pd.DataFrame()


def current_top(fresh, period, market, theme, rank_fn):
    view=fresh.copy()
    if market=='한국 주식': view=view[view.market.isin(['KOSPI','KOSDAQ']) & view.asset_type.eq('STOCK')]
    elif market=='미국 주식': view=view[view.market.isin(['NASDAQ','NYSE/OTHER']) & view.asset_type.eq('STOCK')]
    elif market in ('국내 ETF','미국 ETF'):
        domestic=view.market.fillna('').astype(str).str.upper().isin(['KOSPI','KOSDAQ','KRX','KR ETF']) | view.ticker.fillna('').astype(str).str.upper().str.endswith(('.KS','.KQ'))
        etf=view.asset_type.fillna('').astype(str).str.upper().eq('ETF')
        view=view[etf & (domestic if market=='국내 ETF' else ~domestic)]
    keywords={'반도체':'반도체|semiconductor|nvidia|advanced micro devices|broadcom|하이닉스', 'AI·기술':'ai|artificial intelligence|software|technology|테크|인공지능|마이크로소프트|naver','금융':'bank|financial|finance|은행|금융|증권','헬스케어':'health|pharma|bio|바이오|제약|헬스','배당':'dividend|배당'}
    if theme!='전체': view=view[view.name.fillna('').astype(str).str.contains(keywords[theme],case=False,regex=True)]
    return rank_fn(view,period).head(10) if not view.empty else view


def show(st, fresh, period_options, rank_fn, resolve_symbol, score_guide, glossary):
    import yfinance as yf
    @st.cache_data(ttl=900,show_spinner=False)
    def indices():
        result=[]
        for name,ticker in INDEXES.items():
            try:
                hist=yf.Ticker(ticker).history(period='7d',interval='1d',auto_adjust=False)
                closes=pd.to_numeric(hist['Close'],errors='coerce').dropna()
                if closes.empty: raise ValueError('no prices')
                last=float(closes.iloc[-1]); prev=float(closes.iloc[-2]) if len(closes)>1 else None
                stamp=closes.index[-1]
                result.append((name,last,100*(last/prev-1) if prev else None,str(stamp.date()),datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')))
            except Exception: result.append((name,None,None,'조회 실패',None))
        return result
    @st.cache_data(ttl=1800,show_spinner=False)
    def news(): return fetch_news(MACRO_QUERY,limit=12)
    @st.cache_data(ttl=3600,show_spinner=False)
    def technical(ticker):
        result=get_technical_report(ticker)
        result['분석 완료(KST)']=datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
        return result
    @st.cache_data(ttl=300,show_spinner=False)
    def returns(ticker):
        try:
            bars=yf.Ticker(ticker).history(period='3mo',interval='1d',auto_adjust=True,timeout=10)
            c=bars.Close.dropna(); day=c.index[-1].date(); local=datetime.now(c.index.tz).date() if c.index.tz else None
            today=100*(c.iloc[-1]/c.iloc[-2]-1) if day==local and len(c)>=2 else None
            prior=c.iloc[:-1] if day==local else c
            yesterday=100*(prior.iloc[-1]/prior.iloc[-2]-1) if len(prior)>=2 else None
            return today,yesterday,*[100*(c.iloc[-1]/c.iloc[-1-h]-1) if len(c)>h else None for h in (5,20)]
        except Exception: return (None,)*4

    mode=st.radio('검색 메뉴',['🏆 추천종목 검색','🔎 관심종목 검색'],horizontal=True,key='qp_unified_mode')
    if mode=='🔎 관심종목 검색':
        st.subheader('🔎 관심종목 검색')
        query=st.text_input('종목명 또는 종목코드',placeholder='삼성전자 / 005930.KS / NVDA')
        if st.button('관심종목 분석',type='primary') and query.strip():
            st.session_state['qp_watch_report']=(query.strip(),technical(resolve_symbol(query.strip())))
        stored=st.session_state.get('qp_watch_report')
        if stored and query.strip()==stored[0]:
            result=stored[1]
            if not isinstance(result,dict) or result.get('error'): st.warning(str(result.get('error','분석 실패')) if isinstance(result,dict) else '분석 실패')
            else:
                st.write(f"**{query}** · {result.get('종합 의견','확인 필요')} · 기준일 {result.get('기준일','미확인')}")
                fields=['기준 종가','종합 점수(100)','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가','RSI','MACD']
                st.dataframe(pd.DataFrame([{'항목':f,'분석값':result.get(f,'미확인')} for f in fields]),hide_index=True,use_container_width=True)
                st.caption('마지막 이용 가능한 가격 기준입니다. 실시간 체결가가 아닐 수 있습니다.')
        return

    st.subheader('1. 주요 시장 지수')
    st.caption('일봉의 마지막 제공 가격 기준입니다. 장중에는 잠정 가격일 수 있으며 실시간 체결 지수를 보장하지 않습니다. 조회 결과는 최대 15분 캐시됩니다.')
    grid=st.columns(4)
    for col,(name,price,change,asof,updated) in zip(grid,indices()):
        col.markdown(f"**{name}**")
        col.markdown(f"### {price:,.2f}" if price is not None else '조회 불가')
        if change is not None:
            color='#D32F2F' if change>0 else '#1565C0' if change<0 else '#808080'
            arrow='▲' if change>0 else '▼' if change<0 else '—'
            col.markdown(f'<span style="color:{color};font-weight:600">{arrow} {change:+.2f}%</span>',unsafe_allow_html=True)
        else: col.caption('등락률 미확인')
        col.caption(f'가격 기준일: {asof}')
        col.caption(f'업데이트: {updated} KST' if updated else '업데이트: 조회 실패')
    st.caption('업데이트는 데이터 조회 성공 시각이며 거래소 체결 시각과 다릅니다.')

    st.subheader('2. 글로벌 마켓 브리핑')
    articles,error=news()
    if error: st.info(error)
    elif not articles: st.info('확인 가능한 최근 뉴스가 없습니다.')
    else:
        for a in articles[:5]:
            with st.expander(f"{a['title']} · {a['date']}",expanded=False):
                st.caption(f"출처: {a['source']} · 발표: {a['date']}")
                st.write('기사 제목과 발행 정보를 확인했습니다. 기사 전문은 저작권·제공처 제한으로 이 화면에 수집되지 않았습니다. 아래 원문에서 상세 내용을 확인하세요.')
                st.markdown(f"[기사 원문 열기]({a['url']})")
        st.caption('뉴스는 약 30분 캐시됩니다. 제목만으로 호재·악재를 단정하지 않습니다.')

    st.subheader('3. 추천종목 TOP10')
    with st.form('qp_unified_filter_form'):
        c1,c2,c3=st.columns([2,1,1])
        period=c1.selectbox('투자 기간',period_options,index=1)
        market=c2.selectbox('시장',['전체','한국 주식','미국 주식','국내 ETF','미국 ETF'])
        theme=c3.selectbox('관심 테마',['전체','반도체','AI·기술','금융','헬스케어','배당'])
        submitted=st.form_submit_button('🔍 검색 · 추천종목 TOP10',type='primary',use_container_width=True)
    if submitted: st.session_state['qp_unified_filters']=(period,market,theme)
    active=st.session_state.get('qp_unified_filters')
    if not active:
        st.info('투자 기간·시장·관심 테마를 선택하고 검색을 누르면 추천순위와 상세분석이 나타납니다.')
        return
    period,market,theme=active
    top=current_top(fresh,period,market,theme,rank_fn)
    if top.empty:
        st.warning('조건에 맞는 최근 7일 분석 결과가 없습니다. 조건을 변경해 주세요.'); return
    top=top.copy()
    top['순위']=range(1,len(top)+1)
    top['업데이트 시각 (KST)']=pd.to_datetime(top['scanned_at_utc'],utc=True,errors='coerce').dt.tz_convert('Asia/Seoul').dt.strftime('%Y-%m-%d %H:%M').fillna('미확인')
    def numeric(column): return pd.to_numeric(top[column],errors='coerce') if column in top else pd.Series([float('nan')]*len(top),index=top.index)
    last=numeric('close')
    ret=pd.DataFrame([returns(str(t)) for t in top.ticker],index=top.index,columns=['오늘수익률','전일수익률','5일수익률','20일수익률'])
    table=pd.DataFrame({'순위':top['순위'],'종목':top['name'],'시장구분':top['market'],'추천점수':top['추천 참고점수'],'기술점수':numeric('score'),'최근 저장 가격':last,'분석 완료(KST)':top['업데이트 시각 (KST)']})
    for col in ret: table[col]=ret[col]
    table=table[['순위','종목','시장구분','추천점수','기술점수','최근 저장 가격',*ret.columns,'분석 완료(KST)']]
    def color(v): return 'color: #D32F2F' if pd.notna(v) and v>0 else 'color: #1565C0' if pd.notna(v) and v<0 else 'color: #808080'
    styled=table.style.apply(lambda col: col.map(color),subset=list(ret.columns)).format({c:'{:+.2f}%' for c in ret},na_rep='미확인')
    st.dataframe(styled,hide_index=True,use_container_width=True,column_config={'추천점수':st.column_config.NumberColumn(help='기술점수와 기간별 수익률을 반영하고 변동성에 따라 감점하는 상대 순위 점수입니다. 100점 만점이나 상승 확률이 아니며 음수도 가능합니다.',format='%.1f')})
    st.caption('수익률은 별도 조회한 수정 일봉 기준이며 장중 잠정값일 수 있습니다. 오늘 거래일 가격이 없으면 미확인입니다. 저장 가격 및 추천점수와 조회 기준이 다를 수 있습니다.')
    with st.expander('📱 스마트폰용 TOP10 간편 보기'):
        for r in table.to_dict('records'):
            st.write(f"**{r['순위']}위 {r['종목']}** · 추천 {r['추천점수']}점 · 5일 {r['5일수익률']}")

    st.subheader('4. 추천종목 상세분석')
    chosen=st.selectbox('상세 분석할 종목',list(range(len(top))),format_func=lambda i:f"{i+1}위 · {top.iloc[i]['name']} ({top.iloc[i]['ticker']})",key='qp_unified_detail_choice')
    item=top.iloc[chosen]; ticker=str(item['ticker']); name=str(item['name'])
    if st.button('선택 종목 상세분석 실행',type='primary',key='qp_unified_detail_run'):
        st.session_state['qp_unified_report']=(ticker,technical(ticker))
    stored=st.session_state.get('qp_unified_report')
    if stored and stored[0]==ticker:
        report=stored[1]
        if not isinstance(report,dict) or report.get('error'): st.warning(str(report.get('error','분석 실패')) if isinstance(report,dict) else '분석 실패')
        else:
            st.write(f"**{name}** · {report.get('종합 의견','판단 보류')} · 기술점수 {report.get('종합 점수(100)','미확인')}/100 · 가격 기준일 {report.get('기준일','미확인')} · 분석 완료 {report.get('분석 완료(KST)','미확인')} KST")
            keys=['기준 종가','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가']
            st.dataframe(pd.DataFrame([{'항목':k,'값':report.get(k,'미확인')} for k in keys]),hide_index=True,use_container_width=True)
            with st.expander('기술지표 전체 확인',expanded=False):
                st.dataframe(pd.DataFrame([{'지표':k,'값':f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,float) else str(v),'분석':interpret(k,v,report)} for k,v in report.items() if k not in keys]),hide_index=True,use_container_width=True)
            with st.expander('관련 뉴스 확인',expanded=False):
                related,err=fetch_news(ticker_query(name,ticker),limit=4)
                if err: st.info(err)
                for a in related: st.markdown(f"[{a['title']}]({a['url']}) · {a['date']}")
    from qp_weekly import load, slots, week_start
    import altair as alt
    records=load(); week=week_start(pd.Timestamp.now(tz='Asia/Seoul')); group='|'.join((period,market,theme))
    weeks=sorted({week,*(week_start(x['slot']) for x in records)},reverse=True)
    with st.expander(f'📈 {name}의 주간 추천순위 변화'):
        selected=st.selectbox('조회 주간',weeks,key='qp_week')
        byslot={x['slot']:x for x in records}; points=[]
        for i,slot in enumerate(slots(selected)):
            rec=byslot.get(slot.isoformat()); rows=rec['groups'].get(group,[]) if rec else []
            match=next((r for r in rows if r['ticker']==ticker),None)
            points.append({'회차':i,'시각':f"{['월','화','수','목','금'][i//2]} {slot.hour}시",'순위':match['rank'] if match else 11 if rows else None})
        d=pd.DataFrame(points); labels=d['시각'].tolist()
        chart=alt.Chart(d).mark_line(point=True).encode(x=alt.X('시각:N',sort=labels),y=alt.Y('순위:Q',scale=alt.Scale(domain=[11,1]),axis=alt.Axis(values=list(range(1,12)))),tooltip=['시각','순위']).properties(height=260)
        st.altair_chart(chart,use_container_width=True); st.caption('11은 TOP10 밖, 빈칸은 미실행입니다. 월~금 오전 10시·오후 3시(KST) 예약 실행 기록만 사용합니다. 실제 실행은 지연될 수 있습니다.')
    st.subheader('5. 추천종목 검증')
    selected=st.selectbox('검증 주간',weeks,key='qp_validation_week'); rows=[]
    for rec in records:
        if week_start(rec['slot'])!=selected: continue
        for r in rec['groups'].get(group,[]):
            o=rec['outcomes'].get(r['ticker'],{}); rows.append({'회차':rec['slot'][5:16].replace('T',' '),'종목':r['name'],'순위':r['rank'],'기준일':o.get('base_date'),'기준가':o.get('base'),**{f'{h}일 수익률':o.get(str(h)) for h in (1,5,20)}})
    st.caption('정기 추천 당시 TOP10 전체를 고정합니다. 추천 이후 첫 거래일의 확정 수정종가를 기준으로 그 뒤 1·5·20거래일 수익률을 측정합니다. 실제 체결 수익률은 아닙니다.')
    if not rows: st.info('정기 추천 기록이 아직 없습니다. 새 예약 실행부터 누적됩니다.'); return
    d=pd.DataFrame(rows); summary=[]
    for h in (1,5,20):
        v=pd.to_numeric(d[f'{h}일 수익률'],errors='coerce').dropna(); summary.append({'기간':f'{h}거래일','추천 건수':len(d),'검증 완료':len(v),'평균 수익률(%)':v.mean() if len(v) else None,'상승 적중률(%)':100*(v>0).mean() if len(v) else None})
    st.dataframe(pd.DataFrame(summary).style.format({'평균 수익률(%)':'{:+.2f}%','상승 적중률(%)':'{:.1f}%'},na_rep='검증 대기'),hide_index=True,use_container_width=True)
    st.dataframe(d.style.format({f'{h}일 수익률':'{:+.2f}%' for h in (1,5,20)},na_rep='검증 대기'),hide_index=True,use_container_width=True)
    st.caption('상승 적중률 = 양의 수익률 건수 / 검증 완료 건수. 동일 종목 반복 추천은 독립 표본이 아니며, 미확인 건은 제외합니다. 수수료·세금 미반영. 시장 대비 초과성과나 미래 예측 정확도를 보장하지 않습니다.')


def interpret(k,v,r):
    try:
        n=float(v); close=float(r['기준 종가'])
        if k in ('5일선','20일선','60일선'): return f"기준 가격이 이동평균보다 {(close/n-1)*100:+.1f}% {'높습니다' if close>=n else '낮습니다'}. 추세 참고."
        if k=='RSI(14)': return '과매수 구간, 추격 주의' if n>=70 else '과매도 구간, 반등 보장 없음' if n<=30 else '중립 구간'
        if k=='MACD 히스토그램': return '상승 모멘텀 우세' if n>0 else '하락 모멘텀 우세' if n<0 else '중립'
        if k=='거래량/20일 평균': return f'최근 평균의 {n:.2f}배. '+('거래 활발' if n>1 else '평균 이하')
        if k=='ATR(14)': return f'평균 진폭이 기준가의 {100*n/close:.1f}%. 변동 위험 참고.'
        if '지지 후보' in k or '저항 후보' in k: return f'기준가 대비 {(n/close-1)*100:+.1f}% 수준. 돌파·지지 보장 없음.'
        if '점수' in k: return '해당 기술 조건 충족 정도를 나타내는 점수. 상승 확률 아님.'
    except (ValueError,TypeError,KeyError,ZeroDivisionError): pass
    return {'기준일':'일봉 가격 기준일','통화':'가격 표시 통화','분석 완료(KST)':'실제 분석 완료 한국시간','종합 의견':'기술 조건에 따른 참고 의견','데이터 공급원':'일봉 제공처'}.get(k,'분석 참고 정보')
