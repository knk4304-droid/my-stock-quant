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
                hist=yf.Ticker(ticker).history(period='10d',interval='1d',auto_adjust=False,timeout=12)
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

    mode=st.radio('검색 메뉴',['🏆 추천종목 검색','🔎 관심종목 검색','📖 프로그램 사용 설명서'],horizontal=True,key='qp_unified_mode')
    if mode=='📖 프로그램 사용 설명서':
        from qp_manual_r15 import show as show_manual
        show_manual(st,score_guide,period_options)
        return
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
    st.caption('Yahoo Finance 제공 일봉 기준이며 실시간 지수가 아닙니다. 데이터 제공 지연·휴장·캐시로 수치가 변하지 않을 수 있습니다. 조회 결과는 최대 15분 캐시됩니다.')
    if st.button('🔄 시장 지수 다시 조회',key='qp_indices_refresh',help='15분 캐시를 비우고 시세 공급원에 다시 요청합니다. 공급원 자료가 지연되면 같은 숫자가 나올 수 있습니다.'):
        indices.clear()
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
        try:
            days=(datetime.now(timezone(timedelta(hours=9))).date()-pd.Timestamp(asof).date()).days
            if days>=2: col.warning(f'기준일이 {days}일 전입니다. 휴장 또는 데이터 지연 여부 확인')
        except Exception: pass
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
    st.dataframe(styled,hide_index=True,use_container_width=True,column_config={'추천점수':st.column_config.NumberColumn(help='기술점수와 기간별 수익률을 반영하고 변동성에 따라 감점하는 상대 순위 점수입니다. 상승 확률이 아니며 100점 초과 또는 음수도 가능합니다.',format='%.1f')})
    st.caption('수익률은 별도 조회한 수정 일봉 기준이며 장중 잠정값일 수 있습니다. 오늘 거래일 가격이 없으면 미확인입니다. 저장 가격 및 추천점수와 조회 기준이 다를 수 있습니다.')
    with st.expander('📱 스마트폰용 TOP10 간편 보기'):
        for r in table.to_dict('records'):
            st.write(f"**{r['순위']}위 {r['종목']}** · 추천 {r['추천점수']}점 · 5일 {r['5일수익률']}")

    from qp_weekly import load as load_weekly
    from qp_entry_r16 import show as show_entry
    show_entry(st,load_weekly(),'|'.join((period,market,theme)))
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
            st.caption('통합 상세분석 · 가격 기준일과 분석 완료 시각은 서로 다릅니다. 관찰가는 기술적 참고 수준이며 체결가나 예측가가 아닙니다.')
            st.markdown(detail_html(report), unsafe_allow_html=True)
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
            points.append({'회차':i,'시각':f"{['월','화','수','목','금'][i//2]} {slot.hour}시",'순위':match['rank'] if match else 11 if rows else None,'가격':match.get('price') if match else None,'가격 기준일':match.get('price_date') if match else None})
        d=pd.DataFrame(points); labels=d['시각'].tolist()
        x=alt.X('시각:N',sort=labels,axis=alt.Axis(labelAngle=0,title='예약 시각 (KST)'))
        rank_chart=alt.Chart(d).mark_line(point=True,color='#2563eb').encode(x=x,y=alt.Y('순위:Q',scale=alt.Scale(domain=[11,1]),axis=alt.Axis(values=list(range(1,12)),title='추천 순위',titleColor='#2563eb')),tooltip=['시각','순위'])
        price_chart=alt.Chart(d).mark_line(point=True,color='#dc2626').encode(x=x,y=alt.Y('가격:Q',scale=alt.Scale(zero=False),axis=alt.Axis(orient='right',title='저장 가격 ('+('KRW' if ticker.endswith(('.KS','.KQ')) else 'USD')+')',titleColor='#dc2626')),tooltip=['시각','가격','가격 기준일'])
        st.altair_chart(alt.layer(rank_chart,price_chart).resolve_scale(y='independent').properties(height=300),use_container_width=True)
        st.caption('파란색: 순위(1위가 위), 빨간색: 당시 저장 일봉 가격. 11은 TOP10 밖입니다. 가격 미저장·미실행은 빈칸이며 과거 가격을 임의로 채우지 않습니다.')
        if not d['순위'].notna().any(): st.info('이 조건의 정기 기록이 아직 없습니다. 아래 검증 메뉴에서 기존 기록을 별도로 확인할 수 있습니다.')
    st.subheader('5. 추천종목 검증')
    selected=st.selectbox('검증 주간',weeks,key='qp_validation_week'); rows=[]
    for rec in records:
        if week_start(rec['slot'])!=selected: continue
        for r in rec['groups'].get(group,[]):
            o=rec['outcomes'].get(r['ticker'],{}); rows.append({'회차':rec['slot'][5:16].replace('T',' '),'종목':r['name'],'순위':r['rank'],'기준일':o.get('base_date'),'기준가':o.get('base'),**{f'{h}일 수익률':o.get(str(h)) for h in (1,5,20)}})
    st.caption('정기 추천 당시 TOP10 전체를 고정합니다. 추천 이후 첫 거래일의 확정 수정종가를 기준으로 그 뒤 1·5·20거래일 수익률을 측정합니다. 실제 체결 수익률은 아닙니다.')
    if not rows:
        st.info('선택 주간·조건의 정기 추천 기록이 없습니다. 예약 실행 기록과 기존 기록은 별개입니다.')
    else:
        render_validation(st,rows)
    with st.expander('기존 추천 검증 기록 (별도 기준)',expanded=not rows):
        legacy_validation(st,period)
    from qp_audit_r17 import show as show_audit
    show_audit(st,records,group)


def render_validation(st,rows):
    d=pd.DataFrame(rows); summary=[]
    for h in (1,5,20):
        v=pd.to_numeric(d[f'{h}일 수익률'],errors='coerce').dropna(); summary.append({'기간':f'{h}거래일','추천 건수':len(d),'검증 완료':len(v),'평균 수익률(%)':v.mean() if len(v) else None,'상승 적중률(%)':100*(v>0).mean() if len(v) else None})
    st.dataframe(pd.DataFrame(summary).style.format({'평균 수익률(%)':'{:+.2f}%','상승 적중률(%)':'{:.1f}%'},na_rep='검증 대기'),hide_index=True,use_container_width=True)
    st.dataframe(d.style.format({f'{h}일 수익률':'{:+.2f}%' for h in (1,5,20)},na_rep='검증 대기'),hide_index=True,use_container_width=True)
    st.caption('상승 적중률 = 양의 수익률 건수 / 검증 완료 건수. 동일 종목 반복 추천은 독립 표본이 아니며, 미확인 건은 제외합니다. 수수료·세금 미반영. 시장 대비 초과성과나 미래 예측 정확도를 보장하지 않습니다.')


def interpret(k,v,r):
    import math
    try:
        n=float(v); close=float(r['기준 종가'])
        if not math.isfinite(n) or close<=0: raise ValueError()
        gap=(n/close-1)*100
        if k=='기준 종가': return f"공급원이 제공한 {r.get('기준일','미확인')} 일봉의 마지막 가격입니다. 모든 이동평균, 목표가 및 손실 거리의 비교 기준입니다. 장중 일봉이면 미확정 가격일 수 있으므로 전일 확정 종가나 실시간 체결가로 단정하지 않습니다."
        if k in ('1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가'):
            meaning={'1차 매수 관찰가':'20일 이동평균과 기준가에서 ATR의 절반을 뺀 값 중 낮은 수준으로, 첫 눌림목을 관찰하는 가격입니다.', '2차 매수 관찰가':'최근 지지 후보와 1차 관찰가보다 ATR 절반 낮은 값 중 낮은 수준입니다. 추가 하락 시 지지 여부를 재확인합니다.', '1차 목표 관찰가':'최근 저항 후보와 기준가에 ATR을 더한 값 중 높은 수준입니다. 상승 시 첫 저항과 차익 실현 여부를 관찰합니다.', '2차 목표 관찰가':'1차 목표에 ATR을 더한 값과 기준가에 ATR 두 배를 더한 값 중 높은 수준입니다. 상승 추세 지속 시 추가 관찰 수준입니다.', '손실 제한 참고가':'지지 후보와 2차 관찰가 아래에 ATR 절반의 여유를 둔 참고 수준입니다. 이탈 시 투자 가설을 재검토하며 실제 손실은 더 커질 수 있습니다.'}[k]
            return f'{meaning} 현재 기준가 대비 {gap:+.2f}%입니다. 도달이나 체결을 보장하지 않습니다.'
        if k in ('5일선','20일선','60일선') and n>0:
            days=k[:-2]; diff=(close/n-1)*100
            return f'최근 {days}거래일 종가의 평균으로 { {"5":"단기","20":"중단기","60":"중기"}[days]} 추세를 살핍니다. 기준가는 평균보다 {abs(diff):.2f}% {"높습니다" if diff>0 else "낮습니다" if diff<0 else "차이가 없습니다"}. '+('상승 흐름을 시사하지만 이격이 크면 조정 위험도 확인해야 합니다.' if diff>0 else '평균선 회복 여부를 확인해야 합니다.' if diff<0 else '평균선 부근에서 방향을 확인합니다.')
        if k=='RSI(14)': return f'최근 14기간의 상승·하락 강도를 0~100으로 나타냅니다. 현재 {n:.1f}로 '+('70 이상 과매수 구간입니다. 상승세가 강하지만 추격 매수와 조정 위험에 유의합니다.' if n>=70 else '30 이하 과매도 구간입니다. 매도 압력이 강하며 반등을 보장하지 않습니다.' if n<=30 else '30~70 사이로 극단적 과매수·과매도는 아닙니다. 50을 기준으로 '+('상승' if n>50 else '하락' if n<50 else '중립')+' 강도를 참고합니다.')
        if k=='MACD 히스토그램': return f'12일·26일 지수이동평균 차이인 MACD에서 9일 신호선을 뺀 값입니다. 현재 {n:+.4f}로 '+('MACD가 신호선 위에 있어 상승 모멘텀이 우세합니다.' if n>0 else 'MACD가 신호선 아래에 있어 하락 모멘텀이 우세합니다.' if n<0 else '두 선이 일치합니다.')+' 단일 수치만으로 모멘텀의 증가·감소나 매수 시점을 확정할 수 없습니다.'
        if k=='거래량/20일 평균': return f'최근 일봉 거래량을 20일 평균 거래량으로 나눈 비율입니다. 현재 {n:.2f}배로 평균 대비 {(n-1)*100:+.1f}%입니다. '+('평균보다 거래가 활발합니다.' if n>1 else '평균 이하 거래량입니다.' if n<1 else '평균 수준입니다.')+' 장중 미완성 일봉은 거래량이 적게 보일 수 있으며 가격 방향과 함께 판단합니다.'
        if k=='ATR(14)': return f'최근 14거래일의 실제 가격 변동폭 평균입니다. 현재 {n:,.2f}로 기준가의 {100*n/close:.2f}%입니다. 방향이 아닌 변동 위험을 나타내며 손절 거리와 투자 규모 설정에 활용합니다.'
        if '지지 후보' in k or '저항 후보' in k: return f'마지막 일봉을 제외한 직전 20거래일의 {"최저 저가" if "지지" in k else "최고 고가"}입니다. 기준가 대비 {gap:+.2f}%에 위치합니다. 과거 가격 반응을 참고하는 수준이며 지지나 돌파를 보장하지 않습니다.'
        if k=='기준가 대비 손절 거리(%)': return f'기준가에서 손실 제한 참고가까지의 하락 거리입니다. 현재 {n:.2f}%로, 기준가에 매수했다고 가정한 가격 차이입니다. 실제 진입가·갭 하락·비용에 따라 손실은 달라집니다.'
        scores={'추세 점수(30)':(30,'기준가의 5일선·20일선 상회 여부와 20일선의 60일선 상회 여부'),'진입 시점 점수(25)':(25,'RSI 구간, MACD 히스토그램의 부호 및 직전 대비 변화'),'거래량 점수(20)':(20,'평균 대비 거래량과 직전 일봉 대비 가격 방향'),'위험 관리 점수(25)':(25,'지지 후보, ATR 비율 및 RSI 과매수 여부'),'종합 점수(100)':(100,'추세·진입 시점·거래량·위험 관리 점수의 합계')}
        if k in scores:
            maximum,meaning=scores[k]; return f'{meaning}를 평가합니다. 현재 {n:g}/{maximum}점으로 배점의 {n/maximum*100:.1f}%를 충족했습니다. 기술 조건 점수이며 상승 확률이나 기대 수익률은 아닙니다.'
    except (ValueError,TypeError,KeyError,ZeroDivisionError): pass
    return {'기준일':'가격과 기술지표 계산에 사용한 마지막 일봉 날짜입니다. 분석 실행 날짜와 다를 수 있습니다.','통화':f'가격 표시 단위는 {v}입니다. 환율 변동과 환전 비용은 별도입니다.','분석 완료(KST)':'프로그램이 분석 결과를 생성한 한국시간입니다. 공급원 시세의 실제 갱신 시각과는 다릅니다.','종합 의견':'기술점수 구간에 따른 조건부 참고 의견입니다. 재무·뉴스·시장 위험을 별도로 확인해야 합니다.','데이터 공급원':'일별 시가·고가·저가·종가·거래량 제공처입니다. 지연 또는 미확정 일봉이 포함될 수 있습니다.','조회 티커':'시세 공급원에서 조회한 종목 식별 코드입니다.'}.get(k,'수치가 없거나 해석에 필요한 자료가 부족합니다.' if v is None else '추가 분석 참고 정보입니다.')


def detail_html(report):
    from html import escape
    from qp_manual_r15 import example
    import math
    first=['기준 종가','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가']
    keys=first+[k for k in report if k not in first]
    rows=[]
    for k in keys:
        v=report.get(k); label='기준가 (최근 일봉 가격)' if k=='기준 종가' else k
        value=('미확인' if v is None or isinstance(v,float) and not math.isfinite(v) else f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,float) else str(v))
        rows.append('<tr><td>'+escape(label)+'</td><td>'+escape(value)+'</td><td>'+escape(interpret(k,v,report))+'<br><strong>추가 확인:</strong> '+escape(check_next(k,v,report))+'<br><strong>쉬운 예시:</strong> '+escape(example(k))+'</td></tr>')
    return '<style>.qp-detail13{width:100%;table-layout:fixed;border-collapse:collapse;font-size:0.9rem;line-height:1.6}.qp-detail13 th,.qp-detail13 td{padding:10px 8px;border:1px solid rgba(128,128,128,.28);vertical-align:top;overflow-wrap:anywhere;white-space:normal}.qp-detail13 th{background:rgba(128,128,128,.12);text-align:left}.qp-detail13 td:first-child{font-weight:600}.qp-detail13 td:nth-child(2){font-variant-numeric:tabular-nums;text-align:right}.qp-detail13 tr:nth-child(even){background:rgba(128,128,128,.045)}@media(max-width:600px){.qp-detail13{font-size:.78rem}.qp-detail13 td,.qp-detail13 th{padding:6px 4px}}</style><table class="qp-detail13"><colgroup><col style="width:20%"><col style="width:16%"><col style="width:64%"></colgroup><thead><tr><th>항목 (지표)</th><th>수치</th><th>분석 · 의미와 현재 상태</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


def check_next(k,v,r):
    checks={
      '기준 종가':'가격 기준일과 거래소 장 종료 여부, 증권사 현재 호가를 대조하세요. 장중 가격이면 확정 종가와 달라질 수 있습니다.',
      'RSI(14)':'최근 3~5일 RSI 방향과 주가 고점의 관계를 확인하세요. 70 이상이면 추격보다 조정 후 지지 확인, 30 이하이면 추가 하락 여부와 반등 거래량 확인이 중요합니다.',
      'MACD 히스토그램':'직전 3~5일 히스토그램이 확대되는지 축소되는지, MACD와 신호선 교차가 발생하는지 확인하세요. 양수라도 축소되면 상승 힘이 약해질 수 있습니다.',
      '거래량/20일 평균':'장 종료 후 거래량을 다시 확인하고 상승일과 하락일 거래량을 비교하세요. 돌파 시 거래량 증가가 동반되는지 확인합니다.',
      'ATR(14)':'예정 진입가와 손실 제한가 차이를 ATR과 비교하고, 갭 하락 및 수수료를 감안해 투자 수량을 줄일 필요가 있는지 확인하세요.',
      '종합 점수(100)':'낮은 세부 점수의 원인을 먼저 확인하세요. 실적 발표, 공시, 시장 급락 위험은 이 점수에 직접 반영되지 않습니다.'}
    if k in checks:return checks[k]
    if '매수 관찰가' in k:return '해당 가격 도달만으로 매수하지 말고 지지 유지, 하락 거래량 감소, 반등 거래량 및 악재 여부를 확인하세요.'
    if '목표 관찰가' in k:return '실제 진입가 대비 목표 수익률과 손절 위험을 비교하고 저항 돌파 여부를 확인하세요.'
    if '손실' in k or '손절' in k:return '실제 진입가 기준 손실률과 허용 손실액을 계산하세요. 갭 하락 시 지정 가격 체결은 보장되지 않습니다.'
    if k in ('5일선','20일선','60일선'):return '평균선 기울기와 배열, 최근 이탈·회복 여부를 차트에서 확인하세요. 이격이 큰 상승은 조정 가능성도 고려합니다.'
    if '점수' in k:return '배점 대비 부족한 조건과 실제 지표를 대조하세요. 높은 점수만으로 매수를 확정하지 않습니다.'
    if '후보' in k:return '최근 고점·저점 재시험과 거래량을 확인하세요. 이탈하면 기존 지지·저항 가설을 재검토합니다.'
    return '가격 기준일, 데이터 누락 및 공급원 차이를 확인하세요.'


def legacy_validation(st,period):
    path=DATA/'recommendation_history.csv'
    if not path.exists(): st.info('기존 추천 기록 파일도 없습니다.'); return
    try: d=pd.read_csv(path,dtype={'ticker':str})
    except Exception as e: st.warning('기존 기록 읽기 실패: '+type(e).__name__); return
    if not {'period','recorded_at_utc','ticker'}.issubset(d.columns): st.warning('기존 기록 형식 확인 필요'); return
    d=d[d.period.eq(period)].copy()
    if d.empty: st.info('해당 투자기간의 기존 기록 없음'); return
    d['기록 시각(KST)']=pd.to_datetime(d.recorded_at_utc,utc=True,errors='coerce').dt.tz_convert('Asia/Seoul').dt.strftime('%Y-%m-%d %H:%M')
    st.caption('기존 전체시장 추천 기록입니다. 시장·테마별 정기 기록과 합산하지 않습니다. 기존 진입 기준일과 후속 가격으로 검증한 값이며 실제 거래 성과가 아닙니다.')
    rows=[]
    for h in (1,5,20):
        v=pd.to_numeric(d.get(f'return_{h}d_pct',pd.Series(index=d.index,dtype=float)),errors='coerce')
        base=pd.to_datetime(d.get('entry_date',pd.Series(index=d.index,dtype=object)),errors='coerce'); end=pd.to_datetime(d.get(f'date_{h}d',pd.Series(index=d.index,dtype=object)),errors='coerce')
        v=v.where(end>base).dropna()
        rows.append({'기간':f'{h}거래일','기록':len(d),'검증 완료':len(v),'평균 수익률(%)':round(v.mean(),2) if len(v) else None,'상승 비율(%)':round(100*(v>0).mean(),1) if len(v) else None})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    cols=['기록 시각(KST)','name','ticker','entry_date','entry_close','return_1d_pct','return_5d_pct','return_20d_pct']
    st.dataframe(d[[c for c in cols if c in d]].rename(columns={'name':'종목','ticker':'코드','entry_date':'기준일','entry_close':'기준가','return_1d_pct':'1일 수익률(%)','return_5d_pct':'5일 수익률(%)','return_20d_pct':'20일 수익률(%)'}),hide_index=True,use_container_width=True)
