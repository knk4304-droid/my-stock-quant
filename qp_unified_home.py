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
    def technical(ticker): return get_technical_report(ticker)

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
    top['업데이트 시각 (KST)']=pd.to_datetime(top['scanned_at_utc'],utc=True,errors='coerce').dt.tz_convert('Asia/Seoul').dt.strftime('%m-%d %H:%M').fillna('미확인')
    def numeric(column): return pd.to_numeric(top[column],errors='coerce') if column in top else pd.Series([float('nan')]*len(top),index=top.index)
    last=numeric('close')
    five=numeric('return_5d_pct')
    # 5-day return cannot be interpreted as yesterday's return. Never fabricate a 1-day return.
    table=pd.DataFrame({'순위':top['순위'],'종목':top['name'],'시장구분':top['market'],'추천점수':top['추천 참고점수'],'기술점수':numeric('score'),
       '최근 종가':last,'오늘 수익률(%)':pd.Series([float('nan')]*len(top),index=top.index),'전일 수익률(%)':pd.Series([float('nan')]*len(top),index=top.index),
       '최근 5거래일(%)':five,'최근 20거래일(%)':numeric('return_20d_pct'),'업데이트 시각 (KST)':top['업데이트 시각 (KST)']})
    st.dataframe(table,hide_index=True,use_container_width=True,height=min(450,40+len(table)*36),column_config={
        '추천점수':st.column_config.NumberColumn('추천점수 ⓘ',help=glossary['추천 참고점수'],format='%.1f'),
        '기술점수':st.column_config.NumberColumn('기술점수 ⓘ',help=glossary['기술 점수'],format='%.1f'),
        '최근 종가':st.column_config.NumberColumn('최근 종가 ⓘ',help='마지막으로 저장된 종가이며 실시간 현재가는 아닙니다.',format='%.2f'),
        '오늘 수익률(%)':st.column_config.NumberColumn('오늘(%) ⓘ',help='장중 시세와 직전 종가가 모두 확인되지 않아 미표시'),
        '전일 수익률(%)':st.column_config.NumberColumn('전일(%) ⓘ',help='전일과 전전일 종가가 저장되지 않아 미표시'),
        '업데이트 시각 (KST)':st.column_config.TextColumn('분석 완료(KST) ⓘ',help='시세 체결 시각이 아니라 자동 분석 완료 시각입니다.')})
    st.caption('오늘·전일 수익률은 현재 저장 데이터에 필요한 시계열이 없어 공란입니다. 가격은 실시간이 아닌 최근 종가입니다. 종목마다 기준일이 다를 수 있습니다.')
    with st.expander('📱 스마트폰용 TOP10 간편 보기',expanded=False):
        for r in table.to_dict('records'):
            st.write(f"**{r['순위']}위 {r['종목']}** · {r['시장구분']} · 추천 {r['추천점수']}점 · 5일 {r['최근 5거래일(%)']}%")

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
            st.write(f"**{name}** · {report.get('종합 의견','판단 보류')} · 기술점수 {report.get('종합 점수(100)','미확인')}/100 · 가격 기준일 {report.get('기준일','미확인')}")
            keys=['기준 종가','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가']
            st.dataframe(pd.DataFrame([{'항목':k,'값':report.get(k,'미확인')} for k in keys]),hide_index=True,use_container_width=True)
            with st.expander('기술지표 전체 확인',expanded=False):
                st.dataframe(pd.DataFrame([{'지표':k,'값':str(v)} for k,v in report.items() if k not in keys]),hide_index=True,use_container_width=True)
            with st.expander('관련 뉴스 확인',expanded=False):
                related,err=fetch_news(ticker_query(name,ticker),limit=4)
                if err: st.info(err)
                for a in related: st.markdown(f"[{a['title']}]({a['url']}) · {a['date']}")
    history=rank_history(ticker,period)
    with st.expander(f'📈 {name}의 주간 추천순위 변화',expanded=False):
        if history.empty: st.info('해당 종목의 저장된 순위 기록이 없습니다.')
        else:
            st.dataframe(history,hide_index=True,use_container_width=True)
            st.line_chart(history.set_index('검색 시각')['순위'],height=210)
            st.caption('순위 숫자가 작을수록 상위입니다. 그래프는 저장된 검색 기록만 포함합니다.')

    st.subheader('5. 추천종목 검증')
    st.caption('실제 추천 이후 1·5·20거래일 가격을 관측한 기록만 검증합니다. 미래 수익률이나 매수 적중률을 의미하지 않습니다.')
    path=DATA/'recommendation_history.csv'
    if not path.exists(): st.info('추천 성과 기록이 아직 없습니다.'); return
    try: hist=pd.read_csv(path,dtype={'ticker':str})
    except (OSError,ValueError) as exc: st.warning(f'검증 기록 읽기 실패: {exc}'); return
    hist=hist[hist['ticker'].isin(top['ticker'].astype(str)) & hist['period'].eq(period)].copy()
    if hist.empty: st.info('현재 TOP10과 투자 기간에 해당하는 검증 기록이 없습니다.'); return
    rows=[]
    for _,r in top.iterrows():
        group=hist[hist.ticker.eq(str(r['ticker']))]
        row={'종목':r['name'],'추천 기록':len(group)}
        for days in (1,5,20):
            values=pd.to_numeric(group.get(f'return_{days}d_pct'),errors='coerce').dropna()
            row[f'{days}일 확인']=len(values)
            row[f'{days}일 평균(%)']=round(values.mean(),2) if len(values) else None
        rows.append(row)
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    with st.expander('ⓘ 검증표를 쉽게 읽는 법',expanded=False):
        st.write('추천 기록은 해당 종목이 추천된 횟수입니다. 5일 확인은 추천 이후 5거래일의 가격을 확인할 수 있었던 기록 수입니다. 5일 평균은 확인 가능한 기록의 단순 평균이며, 실제 매매 수익률이 아닙니다.')
        st.write('거래 수수료·세금·슬리피지와 매수 체결 가능성은 반영하지 않습니다. 기록이 적거나 관측이 누락되면 결과가 왜곡될 수 있습니다.')
