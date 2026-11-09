"""Simple, read-only recommendation workspace based on persisted market scans."""
from pathlib import Path
import json
import pandas as pd
from technical_report_v63 import get_technical_report

DATA = Path(__file__).resolve().parent / 'market_scan_data'
PERIODS = ['단기 (1~3일)', '스윙 (1~2주)', '중기 (1~3개월)', '장기 (1년 이상)']

def load_data():
    state_file, scores_file = DATA/'state.json', DATA/'scores.csv'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
    scores = pd.read_csv(scores_file, dtype={'ticker':str}) if scores_file.exists() else pd.DataFrame()
    return state, scores

def rank(frame, period):
    d=frame.copy()
    for k in ('score','return_5d_pct','return_20d_pct','volatility_annual'):
        d[k]=pd.to_numeric(d[k],errors='coerce') if k in d else float('nan')
    r5=d['return_5d_pct'].clip(-25,25).fillna(0)
    r20=d['return_20d_pct'].clip(-40,40).fillna(0)
    vol=d['volatility_annual'].clip(0,3).fillna(1)
    base=d['score'].fillna(0)
    if period.startswith('단기'): score=base*.5+r5*.8-vol*12
    elif period.startswith('스윙'): score=base*.6+r5*.35+r20*.25-vol*10
    elif period.startswith('중기'): score=base*.7+r20*.35-vol*10
    else: score=base*.8+r20*.15-vol*18
    d['추천 참고점수']=score.round(1)
    return d.sort_values('추천 참고점수',ascending=False)

def resolve_symbol(raw):
    """Resolve exact company name/code against saved catalog without a network call."""
    raw=raw.strip()
    if not raw: return ''
    if raw.isdigit() and len(raw)==6: raw=raw+'.KS'
    catalog=DATA/'catalog.csv'
    if catalog.exists():
        try:
            f=pd.read_csv(catalog,dtype=str,usecols=['ticker','name'])
            exact=f[f['name'].fillna('').str.casefold().eq(raw.casefold()) | f['ticker'].fillna('').str.casefold().eq(raw.casefold())]
            if len(exact)==1: return str(exact.iloc[0]['ticker']).upper()
            if raw.endswith('.KS') and not exact.empty: return str(exact.iloc[0]['ticker']).upper()
        except (OSError,ValueError,KeyError): pass
    return raw.upper()

from functools import lru_cache
from datetime import datetime, timezone

@lru_cache(maxsize=512)
def _cached_report_by_day(ticker, day):
    return get_technical_report(ticker)

def cached_report(ticker):
    # Expire cached market data daily rather than holding outdated levels indefinitely.
    return _cached_report_by_day(ticker, datetime.now(timezone.utc).date().isoformat())

def valid_scenario(buy, target, stop):
    if any(v is None or not pd.notna(v) for v in (buy,target,stop)) or buy<=0:
        return False
    return stop < buy < target


def show(st):
    st.markdown('''<style>
    .block-container {max-width: 1450px; padding-top: 1.1rem; padding-left: 1.4rem; padding-right: 1.4rem;}
    html, body, [data-testid="stAppViewContainer"] {font-size: 16px;}
    [data-testid="stDataFrame"] {font-size: 15px;}
    div[data-testid="stMetricValue"] {font-size: 1.55rem;}
    h2, h3 {margin-top: .65rem !important;}
    div[data-testid="stVerticalBlock"] {gap: .55rem;}
    </style>''', unsafe_allow_html=True)
    st.title('📈 AI STOCK MASTER')
    st.caption('한 화면에서 추천 후보 확인 → 종목 선택 → 기술적 매매 시나리오 확인')
    state, scores=load_data()
    if scores.empty:
        st.warning('저장된 시장 분석 결과가 없습니다. GitHub Actions의 Market scan v9을 먼저 실행해 주세요.')
        return
    scores=scores.copy()
    scores['scanned_at_utc']=pd.to_datetime(scores['scanned_at_utc'],utc=True,errors='coerce')
    now=pd.Timestamp.now(tz='UTC')
    scores['분석 경과일']=(now-scores['scanned_at_utc']).dt.total_seconds()/86400
    fresh=scores[scores['분석 경과일'].between(0,7)].copy()
    # A ticker may appear in several saved scan batches; only its newest result is ranked.
    fresh=fresh.sort_values('scanned_at_utc').drop_duplicates(subset=['ticker'],keep='last')
    if fresh.empty:
        st.warning('최근 7일 이내에 분석된 종목이 없습니다. GitHub Actions에서 자동 분석을 실행하세요.')

    a,b,c=st.columns(3)
    a.metric('저장된 분석 종목',f'{len(scores):,}개')
    b.metric('최근 7일 분석',f'{len(fresh):,}개')
    c.metric('최근 실행 성공',f"{state.get('succeeded',0):,}/{state.get('attempted',0):,}개")
    st.caption('저장된 분석은 전체 상장종목을 동시에 분석한 결과가 아닙니다. 최근 실행 성공은 마지막 자동 작업 기준입니다. 동일 종목은 최신 결과 하나만 사용합니다.')
    st.subheader('🏆 추천 후보')
    st.caption('기간별 가격 흐름으로 정렬한 **관찰 후보**입니다. 검증된 상승 확률이나 확정 매수 신호가 아닙니다.')
    c1,c2,c3=st.columns([2,1,1])
    with c1: period=st.selectbox('투자 기간',PERIODS,index=1)
    with c2: market=st.selectbox('시장',['전체','한국 주식','미국 주식','ETF'])
    with c3: theme=st.selectbox('관심 테마',['전체','반도체','AI·기술','금융','헬스케어','배당'])
    query=st.text_input('종목 찾기 (선택)',placeholder='삼성전자 / 005930 / NVDA')
    view=fresh.copy()
    if market=='한국 주식': view=view[view.market.isin(['KOSPI','KOSDAQ']) & view.asset_type.eq('STOCK')]
    elif market=='미국 주식': view=view[view.market.isin(['NASDAQ','NYSE/OTHER']) & view.asset_type.eq('STOCK')]
    elif market=='ETF': view=view[view.asset_type.eq('ETF')]
    # These are keyword themes, not an official sector classification.
    keywords={'반도체':'반도체|semiconductor|nvidia|advanced micro devices|broadcom|하이닉스',
              'AI·기술':'ai|artificial intelligence|software|technology|테크|인공지능|마이크로소프트|naver',
              '금융':'bank|financial|finance|은행|금융|증권',
              '헬스케어':'health|pharma|bio|바이오|제약|헬스',
              '배당':'dividend|배당'}
    if theme!='전체':
        view=view[view['name'].fillna('').astype(str).str.contains(keywords[theme],case=False,regex=True)]
        st.caption('테마는 현재 종목명 키워드로 임시 분류합니다. 정확한 업종·테마 분류는 추후 별도 데이터로 보강해야 합니다.')
    if query.strip():
        mask=view['name'].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False) | view['ticker'].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False)
        view=view[mask]
    ranked=rank(view,period) if not view.empty else view
    st.caption(f'최근 7일 데이터에서 조건에 맞는 종목 {len(ranked):,}개 · 상위 10개 표시')
    cols={'name':'종목명','ticker':'종목코드','market':'시장','score':'기술 점수','return_5d_pct':'최근 5일(%)','return_20d_pct':'최근 20일(%)','asof_price':'가격 기준일'}
    if ranked.empty:
        st.info('조건에 맞는 최근 분석 종목이 없습니다. 시장·테마 조건을 넓히거나 아래 종목 상세 분석을 이용하세요.')
    else:
        st.dataframe(ranked.head(10).rename(columns=cols)[['종목명','종목코드','시장','추천 참고점수','기술 점수','가격 기준일']],hide_index=True,use_container_width=True)
    st.subheader('🔎 상위 10종목 상세 분석 · 매수/매도 참고 구간')
    st.caption('위에서 선택한 기간·시장·테마에 따라 상위 10종목을 분석합니다. 시세 조회는 버튼을 누를 때만 진행하며, 종목당 최대 약 12초가 걸릴 수 있습니다.')
    top = ranked.head(10) if not ranked.empty else pd.DataFrame()
    if not top.empty:
        # Preserve reports across Streamlit reruns; avoid showing stale reports after filters change.
        symbols = tuple(str(t) for t in top['ticker'].tolist())
        if st.button('상위 10종목 상세 분석 실행', type='primary', use_container_width=True):
            progress = st.progress(0, text='상위 종목의 가격 데이터를 확인하고 있습니다.')
            reports = []
            for i, (_, r) in enumerate(top.iterrows()):
                ticker = str(r['ticker'])
                result = cached_report(ticker)
                reports.append((str(r['name']), ticker, result))
                progress.progress((i + 1) / len(top), text=f'{i+1}/{len(top)} 종목 분석 완료')
            st.session_state['simple_batch_reports'] = {'symbols': symbols, 'reports': reports}
            progress.empty()
        stored = st.session_state.get('simple_batch_reports', {})
        if stored.get('symbols') == symbols:
            report_rows = []
            for name, ticker, result in stored['reports']:
                if not isinstance(result, dict) or result.get('error'):
                    report_rows.append({'종목명':name,'코드':ticker,'매매 판단':'분석 불가','분석 점수':None,
                                        '현재가':None,'1차 매수가':None,'1차 목표가':None,'손절 기준가':None,
                                        '예상 상승폭':None,'예상 하락폭':None,'손익비':None,'가격 조건':'확인 불가'})
                    continue
                def numeric(key):
                    try:
                        v=float(result.get(key))
                        return v if pd.notna(v) else None
                    except (TypeError,ValueError): return None
                current=numeric('기준 종가')
                buy=numeric('1차 매수 관찰가')
                target=numeric('1차 목표 관찰가')
                stop=numeric('손실 제한 참고가')
                # Percentage comparisons are anchored to the proposed entry, not today's price.
                upside=round((target/buy-1)*100,1) if buy and target else None
                downside=round((1-stop/buy)*100,1) if buy and stop else None
                scenario_ok=valid_scenario(buy,target,stop)
                rr=round(upside/downside,2) if scenario_ok and upside is not None and downside and downside>0 else None
                report_rows.append({'종목명':name,'코드':ticker,'매매 판단':result.get('종합 의견'),
                                    '분석 점수':numeric('종합 점수(100)'),'현재가':current,
                                    '1차 매수가':buy,'1차 목표가':target,'손절 기준가':stop,
                                    '예상 상승폭':upside if scenario_ok else None,'예상 하락폭':downside if scenario_ok else None,'손익비':rr,'가격 조건':'정상' if scenario_ok else '재검토 필요'})
            st.markdown('**추천 종목 한눈에 비교**')
            if any(r.get('가격 조건')=='재검토 필요' for r in report_rows):
                st.warning('일부 종목의 손절가·매수가·목표가 순서가 맞지 않아 수익·손실 비교를 생략했습니다. 해당 가격은 재검토가 필요합니다.')
            st.caption('상승폭·하락폭은 1차 매수가를 기준으로 계산한 시나리오입니다. 손익비는 예상 상승폭 ÷ 예상 하락폭이며, 실제 수익을 보장하지 않습니다.')
            st.dataframe(pd.DataFrame(report_rows), hide_index=True, use_container_width=True,
                         height=min(430, 40+len(report_rows)*35),
                         column_config={
                             '종목명':st.column_config.TextColumn('종목',width='medium'),
                             '코드':st.column_config.TextColumn('코드',width='small'),
                             '매매 판단':st.column_config.TextColumn('판단',width='medium'),
                             '분석 점수':st.column_config.NumberColumn('점수 /100',format='%.0f'),
                             '현재가':st.column_config.NumberColumn('현재가',format='%.2f'),
                             '1차 매수가':st.column_config.NumberColumn('매수 참고',format='%.2f'),
                             '1차 목표가':st.column_config.NumberColumn('목표 참고',format='%.2f'),
                             '손절 기준가':st.column_config.NumberColumn('손절 참고',format='%.2f'),
                             '예상 상승폭':st.column_config.NumberColumn('상승 여지',format='%+.1f%%'),
                             '예상 하락폭':st.column_config.NumberColumn('손실 위험',format='%.1f%%'),
                             '손익비':st.column_config.NumberColumn('손익비',format='%.2f'),
                             '가격 조건':st.column_config.TextColumn('가격 조건',width='small'),
                         })
            with st.expander('📘 표에 나오는 용어 쉽게 이해하기'):
                st.markdown("""
                - **매매 판단**: 기술적 지표에 따른 관찰 의견입니다. 실제 매수 지시가 아닙니다.
                - **분석 점수**: 추세·매수 시점·거래량·위험 관리를 합산한 100점 만점의 규칙 기반 점수입니다. 상승 확률이 아닙니다.
                - **현재가**: 분석에 사용된 마지막 종가로, 실시간 가격과 다를 수 있습니다.
                - **매수 참고**: 1차 매수를 검토할 가격입니다.
                - **목표 참고**: 1차 매도 목표를 검토할 가격입니다.
                - **손절 참고**: 손실 제한을 검토할 가격입니다.
                - **상승 여지**: 1차 매수가에서 1차 목표가까지의 가격 차이를 백분율로 계산한 값입니다.
                - **손실 위험**: 1차 매수가에서 손절 참고가까지의 가격 차이를 백분율로 계산한 값입니다.
                - **손익비**: 상승 여지 ÷ 손실 위험입니다. 예를 들어 2라면 예상 이익 폭이 예상 손실 폭의 2배입니다.
                - **가격 조건**: 손절가 < 매수가 < 목표가 순서가 맞는지 확인합니다. 맞지 않으면 수익률과 손익비를 계산하지 않습니다.
                - **추천 검증**: 현재 화면의 점수는 과거 가격 기반 지표이며, 추천 이후 실제 수익률·적중률 검증과는 다릅니다.
                """)
            st.markdown('**종목별 분석 결과**')
            for i,(name,ticker,result) in enumerate(stored['reports'],1):
                with st.expander(f'{i}. {name} ({ticker}) · {result.get("종합 의견", "분석 실패")}'):
                    if not isinstance(result,dict) or result.get('error'):
                        st.warning(result.get('error','분석 결과를 불러오지 못했습니다.') if isinstance(result,dict) else '분석 결과 형식이 올바르지 않습니다.')
                        continue
                    st.write(f"**기술 점수 {result.get('종합 점수(100)','-')}점 / 100점** · 가격 기준일 {result.get('기준일','-')} · 통화 {result.get('통화','-')}")
                    def fmt_price(key):
                        try: return f"{float(result[key]):,.2f}"
                        except (TypeError,ValueError,KeyError): return '-'
                    st.markdown(
                        f"**매수 검토** {fmt_price('1차 매수 관찰가')} / {fmt_price('2차 매수 관찰가')}  "
                        f"\n\n**목표 가격** {fmt_price('1차 목표 관찰가')} / {fmt_price('2차 목표 관찰가')}  "
                        f"\n\n**손절 참고** {fmt_price('손실 제한 참고가')}"
                    )
                    with st.expander('전문 기술 지표 보기'):
                        indicators=[
                            ('5일선','최근 5거래일 평균 주가'),
                            ('20일선','최근 20거래일 평균 주가'),
                            ('60일선','최근 60거래일 평균 주가'),
                            ('RSI(14)','최근 상승·하락 강도. 일반적으로 70 이상 과열 가능성, 30 이하 침체 가능성'),
                            ('MACD 히스토그램','주가 추세의 상승·하락 모멘텀을 참고하는 지표'),
                            ('거래량/20일 평균','평소 20일 평균 거래량 대비 몇 배인지'),
                            ('추세 점수(30)','가격 추세의 방향과 강도: 30점 만점'),
                            ('진입 시점 점수(25)','매수 진입 시점의 기술적 조건: 25점 만점'),
                            ('거래량 점수(20)','거래량으로 확인한 신호의 강도: 20점 만점'),
                            ('위험 관리 점수(25)','가격 변동과 손실 위험 조건: 25점 만점'),
                        ]
                        st.dataframe(pd.DataFrame([{'지표':k,'분석값':result.get(k),'쉬운 설명':d} for k,d in indicators]),
                                     hide_index=True,use_container_width=True,height=390,
                                     column_config={'지표':st.column_config.TextColumn(width='medium'),
                                                    '쉬운 설명':st.column_config.TextColumn(width='large')})
            st.warning('매수·목표·손절 가격은 과거 차트로 계산한 참고 구간입니다. 실제 수익률 검증이나 미래 가격 예측이 아닙니다.')
            with st.expander('📊 실제 추천 성과 검증 상태'):
                st.info('현재 이 화면은 추천 후 1일·1주·1개월 실제 수익률과 적중률을 계산하지 않습니다. 추천 당시 종목·가격·시각을 저장하고, 미래 시세가 쌓인 후 비교하는 별도 검증 체계가 필요합니다.')
        else:
            st.info('상위 10종목의 상세 가격 구간과 지표를 보려면 위 분석 실행 버튼을 누르세요.')
    with st.expander('다른 종목 직접 분석'):
        st.caption('상위 10종목 외의 종목도 조회할 수 있습니다. 예: 삼성전자, 005930.KS, NVDA')
        symbol=st.text_input('종목명 또는 코드',placeholder='삼성전자 / 005930.KS / NVDA',key='simple_ticker')
        if st.button('선택 종목 분석'):
            if not symbol.strip():
                st.warning('종목명을 입력해 주세요.')
            else:
                result=cached_report(resolve_symbol(symbol))
                if 'error' in result:
                    st.warning(result['error'])
                else:
                    st.success(f"{result['조회 티커']} · {result['종합 의견']} · 기술 점수 {result['종합 점수(100)']}점")
                    keys=['기준 종가','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가']
                    st.dataframe(pd.DataFrame([{'항목':k,'가격':result[k]} for k in keys]),hide_index=True,use_container_width=True)
    with st.expander('⚙️ 운영 상태 · 분석 범위와 점수 설명'):
        st.write(f"마지막 자동 분석(UTC): {state.get('updated_utc','확인 불가')}")
        st.write(f"검색 가능한 종목 목록: {state.get('catalog_size',0):,}개 · 최근 조회 시도: {state.get('attempted',0):,}개")
        st.write(f"최근 조회 실패: {state.get('failed',0):,}개 · 누적 저장 결과: {len(scores):,}개")
        st.caption('목록 등록, 분석 성공, 최근 데이터 확보는 서로 다른 개념입니다. 현재 점수는 과거 가격 지표의 규칙 기반 평가이며 성과 검증과 별도입니다.')
        if 'market' in scores:
            st.dataframe(scores.groupby('market').size().rename('누적 저장 종목').reset_index(),hide_index=True,use_container_width=True)
        st.caption('안정적 표본 1,200종목 운영은 차기 배치 개선 대상입니다. 현 배치는 전체 종목 목록을 시장별로 순환 조회합니다.')
