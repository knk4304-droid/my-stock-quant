"""Unified recommendation home. Existing scan and watchlist engines remain untouched."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
from market_news import fetch_news, MACRO_QUERY, ticker_query
from technical_report_v63 import get_technical_report
from qp_classic_r22 import chart_url, rolling_points, outcome_status, strategy_rows, safe_report

def stock_link(name,ticker):
    from html import escape
    return f'<a href="{escape(chart_url(ticker),quote=True)}" target="_blank" rel="noopener noreferrer">{escape(str(name))}</a>'

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


def filtered_candidates(fresh, market, theme):
    view=fresh.copy()
    if view.empty:
        return view
    if market=='한국 주식': view=view[view.market.isin(['KOSPI','KOSDAQ']) & view.asset_type.eq('STOCK')]
    elif market=='미국 주식': view=view[view.market.isin(['NASDAQ','NYSE/OTHER']) & view.asset_type.eq('STOCK')]
    elif market in ('국내 ETF','미국 ETF'):
        domestic=view.market.fillna('').astype(str).str.upper().isin(['KOSPI','KOSDAQ','KRX','KR ETF']) | view.ticker.fillna('').astype(str).str.upper().str.endswith(('.KS','.KQ'))
        etf=view.asset_type.fillna('').astype(str).str.upper().eq('ETF')
        view=view[etf & (domestic if market=='국내 ETF' else ~domestic)]
    keywords={'반도체':'반도체|semiconductor|nvidia|advanced micro devices|broadcom|하이닉스', 'AI·기술':'ai|artificial intelligence|software|technology|테크|인공지능|마이크로소프트|naver','금융':'bank|financial|finance|은행|금융|증권','헬스케어':'health|pharma|bio|바이오|제약|헬스','배당':'dividend|배당'}
    if theme!='전체': view=view[view.name.fillna('').astype(str).str.contains(keywords[theme],case=False,regex=True)]
    return view


def current_top(fresh, period, market, theme, rank_fn):
    view = filtered_candidates(fresh, market, theme)
    return rank_fn(view, period).head(10) if not view.empty else view


def refresh_pool(saved, catalog, market, theme, now, limit=60):
    from qp_discovery_r25 import candidate_pool
    from qp_universe_r18 import eligible

    picked = candidate_pool(eligible(saved), limit)
    if len(picked) == limit:
        return picked
    fallback = filtered_candidates(eligible(catalog), market, theme)
    if fallback.empty:
        return picked
    fallback = fallback.loc[~fallback.ticker.isin(picked.get('ticker', ()))].sort_values('ticker')
    groups = fallback.groupby(['market', 'asset_type'], sort=True)
    offset = pd.Timestamp(now).date().toordinal()
    order = (groups.cumcount() - offset) % groups.ticker.transform('size')
    fallback = fallback.loc[order.sort_values(kind='stable').index]
    return pd.concat([picked, fallback], ignore_index=True).head(limit)


def reusable_candidates(frame, now):
    """Reuse only complete, finite inputs collected after the relevant session closed."""
    from qp_current_gate_r60 import latest_completed_session, exchange_zone
    from qp_universe_r18 import eligible
    import numpy as np
    fields=['score','close','return_5d_pct','return_20d_pct','volatility_annual']
    if frame.empty or not set(fields+['ticker','asof_price','scanned_at_utc','market','asset_type','name']).issubset(frame.columns):
        return frame.iloc[0:0].copy()
    d=eligible(frame).copy()
    for k in fields: d[k]=pd.to_numeric(d[k],errors='coerce')
    stamps=pd.to_datetime(d.scanned_at_utc,format='mixed',utc=True,errors='coerce')
    days=pd.to_datetime(d.asof_price,errors='coerce').dt.date
    good=np.isfinite(d[fields]).all(axis=1)&d.score.between(0,100)&d.close.gt(0)&d.volatility_annual.ge(0)&stamps.le(now)
    from exchange_calendars import get_calendar
    for zone,calname,anchor in [('Asia/Seoul','XKRX','^KS11'),('America/New_York','XNYS','^GSPC')]:
        mask=d.ticker.map(exchange_zone).eq(zone)
        day=latest_completed_session(anchor,now)
        close=get_calendar(calname).session_close(pd.Timestamp(day))
        good &= ~mask | (days.eq(day)&stamps.ge(close))
    return d.loc[good].assign(_stamp=stamps[good]).sort_values('_stamp').drop_duplicates('ticker',keep='last').drop(columns='_stamp')


def show(st, fresh, period_options, rank_fn, resolve_symbol, score_guide, glossary):
    import yfinance as yf
    from functools import partial
    from qp_refresh_r23 import refresh_candidates
    from qp_discovery_r25 import valid_prices
    from qp_current_gate_r60 import (completed_bars, exchange_zone, has_current_price,
                                     latest_completed_session)
    from qp_rank_r26 import rank as shared_rank
    def indices():
        from qp_index_live import index_quote
        result=[]
        for name,ticker in INDEXES.items():
            try:
                price,change,asof,status=index_quote(ticker, lambda **kw: yf.Ticker(ticker).history(**kw,auto_adjust=False,timeout=12))
                result.append((name,price,change,f'{asof} · {status}',datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')))
            except Exception:
                previous = st.session_state.get('qp_last_index_quotes', {}).get(ticker)
                if previous:
                    result.append((name,previous[1],previous[2],previous[3]+' · 갱신 실패 (마지막 정상값)',previous[4]))
                else:
                    result.append((name,None,None,'조회 실패',None))
            else:
                st.session_state.setdefault('qp_last_index_quotes', {})[ticker] = result[-1]
        return result
    @st.cache_data(ttl=1800,show_spinner=False)
    def news(): return fetch_news(MACRO_QUERY,limit=12)
    @st.cache_data(ttl=300,show_spinner=False)
    def technical(ticker, session, refresh_token):
        result = safe_report(get_technical_report(ticker, completed_at=pd.Timestamp.now(tz='UTC')))
        if not result.get('error') and not has_current_price(result.get('조회 티커', ticker), result.get('기준일')):
            return {'error': f"최근 종료 거래일 자료 미확보 · 공급원 기준일 {result.get('기준일', '미확인')}"}
        result['분석 완료(KST)']=datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
        return result
    @st.cache_data(ttl=300,show_spinner=False)
    def daily_returns(ticker, session, refresh_token):
        try:
            bars = yf.Ticker(ticker).history(period='10d', interval='1d', auto_adjust=True, timeout=10)
            closes = pd.to_numeric(bars.Close, errors='coerce').dropna().sort_index()
            closes = closes[closes.gt(0) & closes.lt(float('inf'))]
            completed = completed_bars(closes, ticker)
            if len(completed) < 2 or not has_current_price(ticker, completed.index[-1]):
                return None, None
            today = pd.Timestamp.now(tz=exchange_zone(ticker)).date()
            last = closes.index[-1].date()
            if last == today:
                prior = closes.iloc[-3:-1] if last == session else completed.iloc[-2:]
                yesterday = 100 * (prior.iloc[-1] / prior.iloc[-2] - 1) if len(prior) == 2 else None
                return 100 * (closes.iloc[-1] / closes.iloc[-2] - 1), yesterday
            return None, 100 * (completed.iloc[-1] / completed.iloc[-2] - 1)
        except Exception:
            return None, None

    def fresh_candidates(candidates, now):
        from market_batch_v90 import scan_one
        from time import monotonic
        start=monotonic()
        rows=[]; failed=[]; attempted=0
        # Bound network work by elapsed time and provider failures, not a fixed symbol cap.
        while attempted<len(candidates) and monotonic()-start<35:
            chunk=candidates.iloc[attempted:attempted+8]
            updated,errors=refresh_candidates(chunk,partial(scan_one,completed_at=now),limit=len(chunk),now=now)
            rows.append(updated); failed.extend(errors); attempted+=len(chunk)
            if len(errors)==len(chunk): break
        return (pd.concat(rows,ignore_index=True) if rows else candidates.iloc[0:0].copy()),failed,attempted

    st.caption('최근 종료 거래일의 일봉만 추천과 상세 전략에 사용합니다. 전체 시장 재분석은 예약 작업에서 수행합니다.')
    if 'qp_market_refresh_token' not in st.session_state:
        st.session_state['qp_market_refresh_token'] = pd.Timestamp.now(tz='UTC').isoformat()
    refresh_market = st.button('시장 정보 새로고침 (지수·뉴스·추천)', key='qp_refresh_market')
    if refresh_market:
        st.session_state['qp_market_refresh_token'] = pd.Timestamp.now(tz='UTC').isoformat()
        st.session_state.pop('qp_live_candidates', None)
        news.clear()
    refresh_token = st.session_state['qp_market_refresh_token']
    mode=st.radio('검색 메뉴',['🏆 추천종목 검색','🔎 관심종목 검색','📖 프로그램 사용 설명서'],horizontal=True,key='qp_unified_mode')
    if mode=='📖 프로그램 사용 설명서':
        from qp_manual_r15 import show as show_manual
        show_manual(st,score_guide,period_options)
        return
    if mode=='🔎 관심종목 검색':
        st.subheader('🔎 관심종목 검색')
        query=st.text_input('종목명 또는 종목코드',placeholder='삼성전자 / 005930.KS / NVDA')
        analyze = st.button('관심종목 분석', type='primary')
        stored = st.session_state.get('qp_watch_report')
        if query.strip() and (analyze or (stored and stored[0] == query.strip())):
            symbol=resolve_symbol(query.strip())
            if not symbol: st.warning('종목명을 확인하거나 정확한 종목코드를 입력하세요.'); return
            session = latest_completed_session(symbol)
            if analyze or refresh_market:
                technical.clear(symbol, session, refresh_token)
            st.session_state['qp_watch_report'] = (query.strip(), technical(symbol, session, refresh_token))
        stored=st.session_state.get('qp_watch_report')
        if stored and query.strip()==stored[0]:
            result=stored[1]
            if not isinstance(result,dict) or result.get('error'): st.warning(str(result.get('error','분석 실패')) if isinstance(result,dict) else '분석 실패')
            else:
                st.write(f"**{query}** · {result.get('종합 의견','확인 필요')} · 기준일 {result.get('기준일','미확인')}")
                render_detail(st,query,result.get('조회 티커',resolve_symbol(query)),result)
        return

    @st.fragment(run_every=60)
    def render_indices():
        st.subheader('1. 주요 시장 지수')
        st.caption('Yahoo Finance 장중 5분봉 또는 최근 확정 일봉입니다. 실시간 체결값은 아니며 지연될 수 있습니다. 접속·새로고침 시 재조회, 화면 유지 중 60초마다 자동 조회.')
        st.button('🔄 시장 지수 다시 조회',key='qp_indices_refresh',help='시세 공급원에 다시 요청합니다. 공급원 자료가 지연되면 같은 숫자가 나올 수 있습니다.')
        grid=st.columns(4)
        for col,(name,price,change,asof,updated) in zip(grid, indices()):
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

    render_indices()

    st.subheader('2. 글로벌 마켓 브리핑')
    articles,error=news()
    if error: st.info(error); st.markdown('[네이버 증권 뉴스](https://finance.naver.com/news/) · [Yahoo Finance 뉴스](https://finance.yahoo.com/news/)')
    elif not articles: st.info('확인 가능한 최근 뉴스가 없습니다.')
    else:
        for a in articles[:5]:
            with st.expander(f"{a['title']} · {a['date']}",expanded=False):
                st.caption(f"출처: {a['source']} · 발표: {a['date']}")
                st.write('기사 제목과 발행 정보를 확인했습니다. 기사 전문은 저작권·제공처 제한으로 이 화면에 수집되지 않았습니다. 아래 원문에서 상세 내용을 확인하세요.')
                st.markdown(f"[기사 원문 열기]({a['url']})")
        st.caption('뉴스는 약 30분 캐시됩니다. 제목만으로 호재·악재를 단정하지 않습니다.')

    st.subheader('3. 추천종목 TOP10')
    from qp_strategy_menu import ordered_modes, mode_label
    c1,c2,c3,c4=st.columns([1.4,1,1,2.3])
    period=c1.selectbox('투자 기간',period_options,index=1,key='qp_period_choice')
    market=c2.selectbox('시장',['전체','한국 주식','미국 주식','국내 ETF','미국 ETF'],key='qp_market_choice')
    theme=c3.selectbox('관심 테마',['전체','반도체','AI·기술','금융','헬스케어','배당'],key='qp_theme_choice')
    modes=ordered_modes(period)
    previous_mode=st.session_state.get('qp_strategy_selected','종합점수순')
    sort_mode=c4.selectbox('정렬 기준',modes,index=modes.index(previous_mode) if previous_mode in modes else 0,format_func=mode_label,key='qp_strategy_'+str(period))
    st.session_state['qp_strategy_selected']=sort_mode
    submitted=st.button('🔍 검색 · 추천종목 TOP10',type='primary',width='stretch')
    if submitted or 'qp_unified_filters' not in st.session_state:
        st.session_state['qp_unified_filters']=(period,market,theme)
    active=st.session_state['qp_unified_filters']
    if tuple(active[:3])!=(period,market,theme):
        st.info('변경한 투자 조건을 적용하려면 검색을 눌러 주세요.')
        return
    st.caption('권장 기간은 전략 특성에 따른 안내이며 실제 수익률 우위는 검증 중입니다.')
    # R21.1: 전체 적격 후보를 먼저 평가하고 정렬한 후 TOP10으로 제한합니다.
    broad=current_top(fresh,period,market,theme,lambda d,p:rank_fn(d,p).head(len(d)))
    full=valid_prices(broad)
    st.caption(f'최근 가격 및 필수 지표 확인 후보: {len(full):,}개 · 가격 기준일 4일 초과 제외(휴장 시 후보 감소 가능)')
    if not full.empty:
        full=shared_rank(full,period,entry=sort_mode=='현재매수유망순')
    refresh_key=(period,market,theme)
    # User-requested default: refresh on every explicit search, not an optional second click.
    # Never silently substitute an older saved ranking after a failed live refresh.
    previous=st.session_state.get('qp_live_candidates')
    now = pd.Timestamp.now(tz='UTC')
    sessions = (latest_completed_session('^KS11', now), latest_completed_session('^GSPC', now))
    expired=(previous is None or previous[0]!=refresh_key or previous[4:] != (sessions,) or
             now-previous[3]>pd.Timedelta(minutes=5))
    # Initial load, browser reload, explicit search and expired results all trigger a new fetch.
    if submitted or expired:
        st.session_state.pop('qp_live_candidates',None)
        try:
            catalog = pd.read_csv(DATA/'catalog.csv', dtype=str)
        except (OSError, ValueError):
            catalog = pd.DataFrame()
        try:
            stored=pd.read_csv(DATA/'scores.csv',dtype={'ticker':str})
        except (OSError,ValueError):
            stored=broad.copy()
        from qp_universe_r18 import eligible
        stored=filtered_candidates(eligible(stored),market,theme)
        cached=st.session_state.get('qp_reusable_daily',pd.DataFrame())
        reuse=reusable_candidates(pd.concat([stored,cached],ignore_index=True),now)
        reuse=filtered_candidates(reuse,market,theme)
        # Prioritize saved leaders, then rotate across catalog markets.
        missing=stored.loc[~stored.ticker.isin(reuse.get('ticker',[]))] if not stored.empty else stored
        if not missing.empty:
            missing=missing.assign(_priority=pd.to_numeric(missing.score,errors='coerce')).sort_values('_priority',ascending=False).drop(columns='_priority')
        fallback=filtered_candidates(eligible(catalog),market,theme)
        if not fallback.empty:
            fallback=fallback.sort_values('ticker')
            groups=fallback.groupby(['market','asset_type'],sort=True)
            offset=int(now.timestamp()//300)
            order=(groups.cumcount()-offset)%groups.ticker.transform('size')
            fallback=fallback.loc[order.sort_values(kind='stable').index]
        # Interleave saved and new candidates so a large stale backlog cannot starve discovery.
        parts=[]
        for i in range(0,max(len(missing),len(fallback)),6):
            parts.extend([missing.iloc[i:i+6],fallback.iloc[i:i+6]])
        candidates=pd.concat(parts,ignore_index=True).drop_duplicates('ticker') if parts else stored.iloc[0:0].copy()
        if not candidates.empty:
            candidates=candidates.loc[~candidates.ticker.isin(reuse.get('ticker',[]))]
        with st.spinner('저장 데이터 검증 및 추가 후보 조회 중...'):
            updated,failed,attempted=fresh_candidates(candidates,now)
        verified_new=reusable_candidates(updated,now)
        combined=reusable_candidates(pd.concat([reuse,verified_new],ignore_index=True),now)
        st.session_state['qp_reusable_daily']=reusable_candidates(pd.concat([cached,combined],ignore_index=True),now)
        st.session_state['qp_sample_requested']=attempted
        st.session_state['qp_sample_saved']=int(candidates.iloc[:attempted].get('ticker',pd.Series(dtype=str)).isin(stored.get('ticker',[])).sum())
        st.session_state['qp_sample_reused']=len(reuse)
        st.session_state['qp_sample_pending']=len(candidates)-attempted
        st.session_state['qp_sample_new']=len(verified_new)
        st.session_state['qp_sample_total_saved']=len(stored)
        st.session_state['qp_live_candidates']=(refresh_key,combined,failed,now,sessions)
    live=st.session_state.get('qp_live_candidates')
    common=full.iloc[0:0].copy()
    if live and live[0]==refresh_key:
        updated=reusable_candidates(live[1],pd.Timestamp.now(tz='UTC'))
        counts={'eligible':len(updated),'rejected':len(live[1])-len(updated)}
        if pd.Timestamp.now(tz='UTC')-live[3]>pd.Timedelta(minutes=5):
            st.warning('최신 추천 유효기간이 만료됐습니다. 다시 검색해 주세요.')
            full=full.iloc[0:0].copy()
        elif not updated.empty:
            common=filtered_candidates(updated,market,theme)
            full=shared_rank(common,period,entry=sort_mode=='현재매수유망순')
            st.success(f'최신 가격 기준 재평가 {counts["eligible"]}개 · 제외 {counts["rejected"]}개 · 조회 실패 {len(live[2])}개')
        else:
            st.warning(f'최신 가격 검증 후보 0개 · 기준일 제외 {counts["rejected"]}개 · 조회 실패 {len(live[2])}개. 추천을 보류합니다.')
            full=full.iloc[0:0].copy()
    else:
        st.warning('최신 데이터 조회가 완료되지 않았습니다. 현재 추천을 보류합니다.'); full=full.iloc[0:0].copy()
    comparison_all=shared_rank(common,period,challenger=True) if not common.empty else common.copy()
    comparison=comparison_all.head(10)
    with st.expander('평가 대상 및 표본 선정 기준'):
        left=set(full.get('ticker',[])); right=set(comparison_all.get('ticker',[]))
        st.write(f"저장 조건 일치 후보 {st.session_state.get('qp_sample_total_saved',len(broad))}개 · 최신 검증 후보 {len(common)}개 · 기존 모델 {len(left)}개 · 개선 모델 {len(right)}개 · 공통 {len(left & right)}개")
        requested=st.session_state.get('qp_sample_requested',0); saved=st.session_state.get('qp_sample_saved',0)
        st.write(f"재조회 요청 {requested}개 · 저장 후보 {saved}개 · 추가 후보 {requested-saved}개 · 신규 검증 성공 {st.session_state.get('qp_sample_new',0)}개")
        st.write(f'표본 동일 여부: {"동일" if left==right and left else "상이 또는 평가 없음"} · 조회 실패 {len(live[2]) if live else 0}개')
        st.write(f"저장 데이터 재활용 {st.session_state.get('qp_sample_reused',0)}개 · 추가 조회 대기 {st.session_state.get('qp_sample_pending',0)}개")
        st.caption('최신 완료 거래일 저장 데이터 전체 재활용 → 부족 후보 시간 예산 내 추가 조회 → 동일 검증 표본 평가. 전체 시장 전수 평가가 아닙니다.')
        if not common.empty:
            st.dataframe(common.groupby(['market','asset_type']).size().rename('검증 종목 수').reset_index(),hide_index=True)
    from qp_patterns import MODES, rank_pattern
    pattern_mode=sort_mode in MODES
    research_mode=sort_mode=='추세·위험균형순'
    if pattern_mode:
        full=rank_pattern(common,sort_mode)
        st.caption(f'{sort_mode} · 기술 패턴 조건 충족 {len(full)}개 · 성과 검증 중. 실적·재무 미반영.')
    elif research_mode:
        full=comparison_all.copy()
        st.caption('추세·위험균형 순위 · 실전 추천 성과 우위 미검증. 매매전략은 별도 기술 분석 참고값입니다.')
    elif sort_mode in ('최근 5일 수익률순','최근 20일 수익률순','낮은 변동성순') and not full.empty:
        col={'최근 5일 수익률순':'return_5d_pct','최근 20일 수익률순':'return_20d_pct','낮은 변동성순':'volatility_annual'}[sort_mode]
        full=full.sort_values(col,ascending=sort_mode=='낮은 변동성순',kind='stable')
    top=full.head(10)
    if top.empty:
        st.warning('현재 검증된 추천 후보가 없습니다. 조회 상태를 확인하거나 잠시 후 다시 검색해 주세요.')
        from qp_weekly import load
        show_validation(st, load(), '|'.join((period, market, theme)), period)
        return
    top=top.copy().reset_index(drop=True)
    top['순위']=range(1,len(top)+1)
    age=(pd.Timestamp.now(tz='UTC')-pd.to_datetime(top['scanned_at_utc'],utc=True,errors='coerce')).dt.total_seconds()/3600
    if age.isna().any(): st.warning('분석 시각 미확인 종목 포함')
    if age.gt(24).any(): st.warning(f'24시간 초과 저장 분석 {int(age.gt(24).sum())}개 포함 · 최신 수익률과 추천점수의 기준 시각이 다릅니다. 휴장 여부와 정기 스캔 상태를 확인하세요.')
    top['업데이트 시각 (KST)']=pd.to_datetime(top['scanned_at_utc'],utc=True,errors='coerce').dt.tz_convert('Asia/Seoul').dt.strftime('%Y-%m-%d %H:%M').fillna('미확인')
    def numeric(column): return pd.to_numeric(top[column],errors='coerce') if column in top else pd.Series([float('nan')]*len(top),index=top.index)
    last=numeric('close')
    ret = pd.DataFrame([daily_returns(t, latest_completed_session(t), refresh_token) for t in top.ticker],
                       index=top.index, columns=['오늘수익률', '전일수익률'])
    ret['5일수익률'] = top['return_5d_pct']
    ret['20일수익률'] = top['return_20d_pct']
    table=pd.DataFrame({'순위':top['순위'],'종목':top['name'],'통화':top.ticker.map(lambda t:'KRW' if str(t).endswith(('.KS','.KQ')) else 'USD'),'시장구분':top['market'],'추천점수':top['추천 참고점수'],'기술점수':numeric('score'),'검증 일봉 가격':last,'가격 기준일':top['asof_price'],'분석 완료(KST)':top['업데이트 시각 (KST)']})
    for col in ret: table[col]=ret[col]
    allowed={'적극매수','분할매수','관망','매수보류'}
    judgments=top.get('entry_judgment',pd.Series(index=top.index,dtype=object))
    table['매수판단']=judgments.map(lambda v:v if isinstance(v,str) and v in allowed else '재검증 필요')
    st.caption('매수판단은 최신 완료 일봉 기반 조건부 기술 판단이며 실시간 매수 지시가 아닙니다. 신규 지표 미확보 시 재검증 필요로 표시합니다.')
    st.caption('종목명을 누르면 차트가 새 탭에서 열립니다. 가격은 검증 일봉 기준입니다.')
    headers=['순위','종목','추천','기술','가격','오늘%','전일%','5일%','20일%','매수판단','분석']
    widths=[.5,2.5,.8,.8,1.2,.8,.8,.8,.8,1.3,1]
    for col,label in zip(st.columns(widths),headers): col.markdown(f'**{label}**')
    for i,r in table.iterrows():
        cols=st.columns(widths)
        cols[0].write(int(r['순위']))
        cols[1].markdown(stock_link(r['종목'],top.loc[i,'ticker']),unsafe_allow_html=True)
        cols[1].caption(f"{r['시장구분']} · {r['가격 기준일']} · {r['분석 완료(KST)']}")
        for col,k in zip(cols[2:9],['추천점수','기술점수','검증 일봉 가격','오늘수익률','전일수익률','5일수익률','20일수익률']):
            v=r.get(k); col.write(f'{v:,.2f}' if pd.notna(v) else '—')
        cols[9].write(r['매수판단'])
        cols[4].caption(r['통화'])
        if cols[10].button('상세',key='top_detail_'+str(top.loc[i,'ticker'])):
            st.session_state['qp_selected_ticker']=str(top.loc[i,'ticker'])
    with st.expander('📱 스마트폰용 TOP10 간편 보기'):
        for i,r in table.iterrows():
            st.markdown(stock_link(r['종목'],top.loc[i,'ticker']),unsafe_allow_html=True)
            st.write(f"{r['순위']}위 · 추천 {r['추천점수']} · 5일 {r['5일수익률']}% · {r['매수판단']}")
    # Details are shown directly below the recommendation table, not in a duplicate menu.
    selected=st.session_state.get('qp_selected_ticker')
    if selected and selected in set(top.ticker.astype(str)):
        item=top.loc[top.ticker.astype(str)==selected].iloc[0]
        ticker=str(item['ticker']); name=str(item['name'])
        st.subheader(f'📌 {name} · 매매 전략 및 상세 분석')
        if research_mode:
            from qp_rank_r26 import challenger_components
            st.caption('개선 모델 평가 근거 · 연구용')
            st.dataframe(pd.DataFrame([challenger_components(item,period)]),hide_index=True)
        report=technical(ticker, latest_completed_session(ticker), refresh_token)
        if not isinstance(report,dict) or report.get('error'):
            st.warning(str(report.get('error','분석 실패')) if isinstance(report,dict) else '분석 실패')
        else:
            asof=report.get('기준일','미확인')
            analyzed=report.get('분석 완료(KST)','미확인')
            scanned=item.get('업데이트 시각 (KST)','미확인')
            st.caption(f'가격·지표 기준 거래일: {asof} | 종목 스캔: {scanned} KST | 상세 분석 실행: {analyzed} KST')
            try:
                # Calendar age alone must not mark a weekend or holiday close as stale.
                age=pd.Timestamp.now(tz='Asia/Seoul').date()-pd.Timestamp(asof).date()
                if age.days>4: st.warning('마지막 확정 일봉이 4일 이상 지났습니다. 휴장·거래 정지·공급원 지연 여부를 확인하기 전에는 신규 매수를 보류하세요.')
            except (ValueError,TypeError): st.warning('가격 기준일을 확인할 수 없습니다. 신규 매수를 보류하세요.')
            st.markdown(f"**현재 판단:** {report.get('종합 의견','판단 보류')} · **기술 점수:** {report.get('종합 점수(100)','미확인')}/100")
            def fmt(key):
                try: return f"{float(report[key]):,.2f}"
                except (ValueError,TypeError,KeyError): return '미확인'
            c1,c2,c3=st.columns(3)
            c1.metric('매수 관찰가',fmt('1차 매수 관찰가'))
            c2.metric('목표 관찰가',fmt('1차 목표 관찰가'))
            c3.metric('손절 참고가',fmt('손실 제한 참고가'))
            st.markdown('**투자 기간별 대응 전략**')
            st.dataframe(pd.DataFrame(strategy_rows(report)),hide_index=True,width='stretch')
            st.caption('조건부 기술적 참고 가격입니다. 실시간 호가·체결가나 미래 수익을 보장하지 않습니다.')
            with st.expander('ⓘ RSI·MACD 등 기술 지표와 설명 펼쳐보기',expanded=False):
                st.markdown(detail_html(report),unsafe_allow_html=True)
            with st.expander('관련 뉴스와 차트',expanded=False):
                st.link_button('차트 열기',chart_url(ticker))
                related,err=fetch_news(ticker_query(name,ticker),limit=4)
                if err: st.info(err)
                for article in related: st.markdown(f"[{article['title']}]({article['url']}) · {article['date']}")
    else:
        st.caption('상세 분석을 보려면 위 추천 표의 상세 버튼을 누르세요.')
    ticker=selected if selected in set(top.ticker.astype(str)) else str(top.iloc[0]['ticker'])
    name=str(top.loc[top.ticker.astype(str)==ticker].iloc[0]['name'])
    from qp_weekly import load
    import altair as alt
    records=load(); group='|'.join((period,market,theme))
    with st.expander(f'📈 {name}의 최근 추천순위 변화'):
        st.caption('저장된 종합점수순 정기·수동 추천 기록 기준입니다. 현재매수유망순 화면의 순위와 다를 수 있습니다.')
        days=st.selectbox('최근 조회 기간',[7,14,30],format_func=lambda n:f'최근 {n}일',key='qp_rolling_days')
        d=rolling_points(records,group,ticker,pd.Timestamp.now(tz='Asia/Seoul'),days)
        labels=d['시각'].tolist()
        x=alt.X('시각:N',sort=labels,axis=alt.Axis(labelAngle=-45,title='추천 기록 시각 (KST)'))
        rank_chart=alt.Chart(d).mark_line(point=True,color='#2563eb').encode(x=x,y=alt.Y('순위:Q',scale=alt.Scale(domain=[11,1]),axis=alt.Axis(values=list(range(1,12)),title='추천 순위',titleColor='#2563eb')),tooltip=['시각','순위'])
        price_chart=alt.Chart(d).mark_line(point=True,color='#dc2626').encode(x=x,y=alt.Y('가격:Q',scale=alt.Scale(zero=False),axis=alt.Axis(orient='right',title='저장 가격 ('+('KRW' if ticker.endswith(('.KS','.KQ')) else 'USD')+')',titleColor='#dc2626')),tooltip=['시각','가격','가격 기준일'])
        if not d.empty: st.altair_chart(alt.layer(rank_chart,price_chart).resolve_scale(y='independent').properties(height=300),width="stretch")
        st.caption('파란색: 순위(1위가 위), 빨간색: 당시 저장 일봉 가격. 11은 TOP10 밖입니다. 미실행 회차는 표시하지 않으며 가격 미저장은 빈칸입니다. 과거 가격을 임의로 채우지 않습니다.')
        if not d['순위'].notna().any(): st.info('이 조건의 정기 기록이 아직 없습니다. 아래 검증 메뉴에서 기존 기록을 별도로 확인할 수 있습니다.')
    show_validation(st, records, group, period)


def show_validation(st, records, group, period):
    from qp_weekly import week_start

    week = week_start(pd.Timestamp.now(tz='Asia/Seoul'))
    weeks = sorted({week, *(week_start(x['slot']) for x in records)}, reverse=True)
    st.subheader('5. 추천종목 검증')
    selected=st.selectbox('검증 주간',['전체 기록',*weeks],key='qp_validation_week'); rows=[]
    for rec in records:
        if selected!='전체 기록' and week_start(rec['slot'])!=selected: continue
        for r in rec['groups'].get(group,[]):
            o=rec['outcomes'].get(r['ticker'],{}); rows.append({'회차':rec['slot'][5:16].replace('T',' '),'종목':r['name'],'순위':r['rank'],'기준일':o.get('base_date'),'기준가':o.get('base'),'검증 상태':outcome_status(o),**{f'{h}일 수익률':o.get(str(h)) for h in (1,5,20)}})
    st.caption('종합점수순 저장 기록 기준입니다. 정기 추천 당시 TOP10 전체를 고정합니다. 추천 이후 첫 거래일의 확정 수정종가를 기준으로 그 뒤 1·5·20거래일 수익률을 측정합니다. 실제 체결 수익률은 아닙니다.')
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
    st.dataframe(pd.DataFrame(summary).style.format({'평균 수익률(%)':'{:+.2f}%','상승 적중률(%)':'{:.1f}%'},na_rep='검증 대기'),hide_index=True,width="stretch")
    st.dataframe(d.style.format({f'{h}일 수익률':'{:+.2f}%' for h in (1,5,20)},na_rep='검증 대기'),hide_index=True,width="stretch")
    st.caption('검증 상태는 마지막 추적 결과입니다. 기존 기록의 미확인 상태는 다음 추적 실행에서 갱신됩니다.')
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
    st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
    cols=['기록 시각(KST)','name','ticker','entry_date','entry_close','return_1d_pct','return_5d_pct','return_20d_pct']
    st.dataframe(d[[c for c in cols if c in d]].rename(columns={'name':'종목','ticker':'코드','entry_date':'기준일','entry_close':'기준가','return_1d_pct':'1일 수익률(%)','return_5d_pct':'5일 수익률(%)','return_20d_pct':'20일 수익률(%)'}),hide_index=True,width="stretch")


def render_detail(st,name,ticker,report):
    from qp_r21_summary import summarize
    st.link_button('선택 종목 실시간·지연 차트 열기',chart_url(ticker))
    try:
        age=(pd.Timestamp.now(tz='Asia/Seoul').date()-pd.Timestamp(report['기준일']).date()).days
        if age>4: st.warning(f'가격 기준일이 {age}일 전입니다. 휴장·시세 지연 여부를 확인하세요.')
    except (KeyError,ValueError,TypeError): pass
    st.markdown(summarize(report))
    st.markdown(detail_html(report),unsafe_allow_html=True)
    st.markdown('**투자 기간별 매수·매도 대응 전략**')
    st.dataframe(pd.DataFrame(strategy_rows(report)),hide_index=True,width="stretch")
    st.caption('공통 일봉 기술지표를 활용한 조건부 대응이며 기간별 독립 검증 모델이나 확정 매매 신호가 아닙니다.')
    with st.expander('관련 뉴스 확인',expanded=False):
        related,err=fetch_news(ticker_query(name,ticker),limit=4)
        if err: st.info(err)
        for a in related: st.markdown(f"[{a['title']}]({a['url']}) · {a['date']}")
