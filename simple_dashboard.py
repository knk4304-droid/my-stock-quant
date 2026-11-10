"""Simple, read-only recommendation workspace based on persisted market scans."""
from pathlib import Path
import json
import pandas as pd
from technical_report_v63 import get_technical_report
from market_news import display_briefing, display_company_brief, MACRO_QUERY, ticker_query

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
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

def format_kst(value):
    """Convert stored ISO-8601 UTC timestamps to readable Korea local time."""
    if value is None or pd.isna(value) or not str(value).strip():
        return "확인 불가"
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(KST)
        ampm = "오전" if local.hour < 12 else "오후"
        hour = local.hour % 12 or 12
        return f"{local.year}년 {local.month}월 {local.day}일 {ampm} {hour}시 {local.minute:02d}분 {local.second:02d}초"
    except (TypeError, ValueError, OverflowError):
        return "확인 불가"


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


def indicator_explanations():
    """Shared plain-language guide for both recommendation and watchlist reports."""
    return [
        ('5일선','최근 5거래일 종가의 평균입니다. 예: 5일 평균 10만원인데 현재가 10만5천원이면 단기 평균보다 5% 높습니다. 위에 있다고 무조건 상승하는 것은 아닙니다.'),
        ('20일선','최근 20거래일 평균 종가로 약 한 달의 흐름을 봅니다. 예: 5일선이 20일선 위로 올라오면 단기 흐름이 개선됐을 가능성을 살펴봅니다. 거짓 신호도 있습니다.'),
        ('60일선','최근 60거래일 평균 종가로 약 3개월의 큰 흐름을 봅니다. 예: 현재가가 60일선보다 계속 낮다면 중기 하락 추세일 수 있습니다.'),
        ('RSI(14)','최근 14거래일의 상승·하락 강도를 0~100으로 나타냅니다. 예: 78은 최근 상승이 강해 과열 가능성을 점검할 구간, 25는 약세가 강해 반등 가능성과 추가 하락 위험을 함께 볼 구간입니다. 70 이상이 곧 매도, 30 이하가 곧 매수는 아닙니다.'),
        ('MACD 히스토그램','단기와 장기 이동평균의 차이로 추세의 변화 속도를 살펴봅니다. 예: 음수 -2000에서 -500으로 오르면 하락 압력이 줄어드는 모습일 수 있지만, 아직 상승 전환이 확정된 것은 아닙니다. 값의 크기는 종목 가격 수준에 따라 달라집니다.'),
        ('거래량/20일 평균','오늘 거래량을 최근 20거래일 평균 거래량으로 나눈 배수입니다. 예: 0.42는 평소의 42% 수준, 2.0은 평소의 2배입니다. 거래량 증가만으로 매수·매도를 결정하지 않습니다.'),
        ('추세 점수(30)','이 프로그램이 이동평균 등 가격 흐름을 규칙으로 평가한 30점 만점 점수입니다. 예: 0점은 현재 규칙에서 추세 조건이 좋지 않다는 뜻이며 향후 상승 확률 0%가 아닙니다.'),
        ('진입 시점 점수(25)','현재 가격이 기술적 매수 관찰 조건에 얼마나 부합하는지 평가한 25점 만점 점수입니다. 예: 10점은 일부 조건만 충족한 상태로, 지금 사야 한다는 의미가 아닙니다.'),
        ('거래량 점수(20)','거래량이 가격 움직임을 얼마나 뒷받침하는지 정해진 규칙으로 평가한 20점 만점 점수입니다. 예: 거래량이 평소보다 적으면 신호 확신이 낮아질 수 있습니다.'),
        ('위험 관리 점수(25)','가격 변동성·손실 위험 조건을 규칙으로 평가한 25점 만점 점수입니다. 예: 15점은 위험이 없다는 뜻이 아니라 일부 위험 조건을 충족했다는 뜻입니다.'),
    ]

def show(st):
    st.markdown('''<style>
    .block-container {max-width: 1450px; padding-top: 1.1rem; padding-left: 1.4rem; padding-right: 1.4rem;}
    html, body, [data-testid="stAppViewContainer"] {font-size: 16px;}
    [data-testid="stDataFrame"] {font-size: 15px;}
    div[data-testid="stMetricValue"] {font-size: 1.55rem;}
    h2, h3 {margin-top: .65rem !important;}
    div[data-testid="stVerticalBlock"] {gap: .55rem;}
    </style>''', unsafe_allow_html=True)
    # Contextual explanations: hover over the ⓘ beside labels/column headers.
    glossary = {
        '저장된 분석 종목':'과거 자동 분석에서 저장된 결과 행 수입니다. 전체 상장종목 수나 오늘 분석한 수와 다릅니다.',
        '최근 7일 분석':'최근 7일 안에 분석한 서로 다른 종목 수입니다. 분석이 성공했다고 수익성이 검증된 것은 아닙니다.',
        '최근 실행 성공':'가장 최근 자동 실행에서 조회에 성공한 종목 수 / 조회를 시도한 종목 수입니다.',
        '추천 참고점수':'선택한 투자 기간의 가격 흐름 등을 기준으로 순위를 정하는 참고 점수입니다. 상승 확률이나 실제 수익률이 아닙니다.',
        '기술 점수':'이동평균·추세·거래량·위험 등의 규칙 기반 평가 점수입니다. 추천 참고점수와 산식 및 목적이 다릅니다.',
        '매매 판단':'과거 기술 지표에 따른 관찰 의견으로 매수·매도 주문 지시가 아닙니다.',
        '손익비':'1차 매수가를 기준으로 예상 상승폭을 예상 하락폭으로 나눈 값입니다. 수익 실현 가능성은 반영하지 않습니다.',
        '예상 상승폭':'1차 매수가 대비 1차 목표가까지의 가정된 상승률입니다. 미래 수익률 예측이 아닙니다.',
        '예상 하락폭':'1차 매수가 대비 손절 참고가까지의 가정된 하락률입니다. 실제 손실은 더 커질 수 있습니다.',
        '가격 조건':'손절 참고가 < 1차 매수가 < 1차 목표가인지 확인합니다. 잘못된 순서이면 손익비를 표시하지 않습니다.',
        '누적 추천 기록':'기록된 추천 건수입니다. 동일 종목이 여러 날짜·기간에 기록되면 각각 포함될 수 있습니다.',
        '이후 가격 확인':'추천 이후 가격을 확보하여 관측 수익률 계산이 가능한 기록 수입니다.',
        '관측 결과 평균':'관측 가능한 기록만 대상으로 계산한 단순 평균 가격 변화율입니다. 실제 계좌 수익률이 아닙니다.',
        '유효 추천':'성과 검증 기준을 만족하는 추천 기록 수입니다. 중복·오류 제거 규칙의 영향을 받습니다.',
        '관측 완료':'추천 이후 지정 거래일의 가격이 확보되어 수익률 계산이 완료된 기록 수입니다.',
        '관측률(%)':'유효 추천 중 지정 거래일의 결과를 확보한 비율입니다.',
        '서로 다른 추천일':'추천이 발생한 고유 날짜 수입니다. 같은 날 여러 종목을 추천해도 1일로 셉니다.',
        '서로 다른 종목':'추천 기록에 포함된 고유 종목 수입니다.',
        '중앙값(%)':'관측 수익률을 정렬했을 때 가운데 값으로, 일부 큰 상승·하락의 영향을 평균보다 덜 받습니다.',
        '상승 비율(%)':'관측 수익률이 0%를 초과한 기록의 비율입니다. 실제 매매 승률과 다릅니다.',
        '95% 탐색구간':'관측된 추천일을 단위로 재표집해 얻는 평균 수익률의 탐색적 불확실성 구간입니다. 미래 수익을 보장하지 않습니다.',
        '판정':'관측 건수·추천일 수·종목 수·관측률 등 통계 검증 요건의 충족 상태입니다.',
        '추천 기준일':'추천에 사용한 기준 가격의 거래일입니다. 기록 시각과 다를 수 있습니다.',
        '기준 종가':'분석에 사용한 거래일의 종가입니다. 실시간 시세가 아닙니다.',
        '관측 수익률(%)':'추천 기준 종가 대비 이후 확인된 종가의 변화율입니다. 실제 매매 손익이 아닙니다.',
        '경과 일수':'추천 기준일 이후 경과한 날짜 수입니다. 거래일 수와 다를 수 있습니다.',
        'RSI(14)':'14개 거래일의 상승·하락 강도를 나타냅니다. 통상 70 이상은 과열, 30 이하는 침체 가능성으로 참고합니다.',
        'MACD 히스토그램':'추세 모멘텀 변화를 나타내는 지표입니다. 단독으로 매매를 결정하면 안 됩니다.',
        '거래량/20일 평균':'최근 거래량을 20거래일 평균 거래량으로 나눈 배수입니다.',
        '슬리피지':'주문 당시 예상한 가격과 실제 체결 가격 사이의 차이입니다.',
        '추천 기록 시각':'프로그램이 추천 내용을 저장한 시각입니다. 한국시간으로 표시하며, 실제로 주식을 산 시간은 아닙니다.',
        '투자 기간':'단기·스윙·중기·장기 등 분석 목적에 따라 나눈 구분입니다. 그 기간에 반드시 매도해야 한다는 뜻은 아닙니다.',
        '종목명':'주식이나 ETF의 이름입니다. 같은 종목도 여러 번 추천 기록에 등장할 수 있습니다.',
        '종목코드':'종목을 구별하는 고유 기호입니다. 예: 삼성전자 005930.KS, 엔비디아 NVDA.',
        '이후 관측일':'추천 기준일 이후 가격을 다시 확인한 거래일입니다. 달력 날짜와 거래일은 다릅니다.',
        '이후 종가':'이후 관측일의 장 마감 가격입니다. 실제 매도 체결 가격이 아닙니다.',
        '기간':'추천 이후 1·5·20거래일 중 어느 시점의 성과를 확인하는지 나타냅니다. 휴장일은 거래일에 포함하지 않습니다.',
        '평균 수익률(%)':'관측된 추천들의 기준 종가 대비 이후 종가 변화율을 평균한 값입니다. 실제 계좌 수익률이 아닙니다.',
        '95% 하한':'탐색적 95% 구간의 아래쪽 경계입니다. 관측 표본이 충분해야 계산되며, 최악의 손실을 뜻하지 않습니다.',
        '95% 상한':'탐색적 95% 구간의 위쪽 경계입니다. 미래 최대 수익을 뜻하지 않습니다.',
        '추천 기록':'해당 투자 기간으로 저장된 추천 건수입니다. 같은 종목이 여러 날짜에 중복될 수 있습니다.',
        '1일 확인':'추천 후 1거래일 가격을 확보한 기록 수입니다. 달력상 다음 날과 다를 수 있습니다.',
        '5일 확인':'추천 후 5거래일 가격을 확보한 기록 수입니다. 아직 5거래일이 지나지 않았다면 0건일 수 있습니다.',
        '20일 확인':'추천 후 20거래일 가격을 확보한 기록 수입니다. 아직 20거래일이 지나지 않았다면 0건일 수 있습니다.',
        '1일 평균(%)':'1거래일 후 가격이 확인된 추천들의 평균 가격 변화율입니다. 실제 매매 수익률이 아닙니다.',
        '5일 평균(%)':'5거래일 후 가격이 확인된 추천들의 평균 가격 변화율입니다. 실제 매매 수익률이 아닙니다.',
        '20일 평균(%)':'20거래일 후 가격이 확인된 추천들의 평균 가격 변화율입니다. 실제 매매 수익률이 아닙니다.',
    }
    def explained_column(label, *, numeric=False, fmt=None, width=None, key=None):
        title = label + (' ⓘ' if label in glossary else '')
        kwargs = {'help': glossary[label]} if label in glossary else {}
        if width is not None: kwargs['width'] = width
        if numeric and fmt is not None: kwargs['format'] = fmt
        return (st.column_config.NumberColumn(title, **kwargs) if numeric
                else st.column_config.TextColumn(title, **kwargs))
    st.title('📈 AI STOCK MASTER')
    st.caption('테마별 종목 추천과 관심종목 검색·분석을 구분한 투자 판단 참고 화면')
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
    a.metric('저장된 분석 종목',f'{len(scores):,}개',help=glossary['저장된 분석 종목'])
    b.metric('최근 7일 분석',f'{len(fresh):,}개',help=glossary['최근 7일 분석'])
    c.metric('최근 실행 성공',f"{state.get('succeeded',0):,}/{state.get('attempted',0):,}개",help=glossary['최근 실행 성공'])
    st.caption('저장된 분석은 전체 상장종목을 동시에 분석한 결과가 아닙니다. 최근 실행 성공은 마지막 자동 작업 기준입니다. 동일 종목은 최신 결과 하나만 사용합니다.')
    recommendation_tab, watchlist_tab, news_tab = st.tabs(['📈 테마별 종목 추천', '🔎 관심종목 검색', '📰 시장 뉴스·공시'])
    with recommendation_tab:
        st.subheader('테마별 종목 추천')
        st.caption('기간별 가격 흐름으로 정렬한 **관찰 후보**입니다. 검증된 상승 확률이나 확정 매수 신호가 아닙니다.')
        c1,c2,c3=st.columns([2,1,1])
        with c1: period=st.selectbox('투자 기간',PERIODS,index=1,help='단기·스윙·중기 등 추천 순위를 계산할 기간입니다. 투자 기간별 추천 참고점수가 달라질 수 있습니다.')
        with c2: market=st.selectbox('시장',['전체','한국 주식','미국 주식','국내 ETF','미국 ETF'])
        with c3: theme=st.selectbox('관심 테마',['전체','반도체','AI·기술','금융','헬스케어','배당'])
        view=fresh.copy()
        if market=='한국 주식': view=view[view.market.isin(['KOSPI','KOSDAQ']) & view.asset_type.eq('STOCK')]
        elif market=='미국 주식': view=view[view.market.isin(['NASDAQ','NYSE/OTHER']) & view.asset_type.eq('STOCK')]
        elif market in ('국내 ETF','미국 ETF'):
            # ETF country is based on listing market, not underlying holdings.
            # Korean tickers may carry .KS/.KQ suffixes even if market metadata is missing.
            is_korean_listing = (
                view['market'].fillna('').astype(str).str.upper().isin(['KOSPI','KOSDAQ','KRX'])
                | view['ticker'].fillna('').astype(str).str.upper().str.endswith(('.KS','.KQ'))
            )
            is_etf = view['asset_type'].fillna('').astype(str).str.upper().eq('ETF')
            view = view[is_etf & (is_korean_listing if market=='국내 ETF' else ~is_korean_listing)]
        # These are keyword themes, not an official sector classification.
        keywords={'반도체':'반도체|semiconductor|nvidia|advanced micro devices|broadcom|하이닉스',
                  'AI·기술':'ai|artificial intelligence|software|technology|테크|인공지능|마이크로소프트|naver',
                  '금융':'bank|financial|finance|은행|금융|증권',
                  '헬스케어':'health|pharma|bio|바이오|제약|헬스',
                  '배당':'dividend|배당'}
        if theme!='전체':
            view=view[view['name'].fillna('').astype(str).str.contains(keywords[theme],case=False,regex=True)]
            st.caption('테마는 현재 종목명 키워드로 임시 분류합니다. 정확한 업종·테마 분류는 추후 별도 데이터로 보강해야 합니다.')
        ranked=rank(view,period) if not view.empty else view
        st.caption(f'최근 7일 데이터에서 조건에 맞는 종목 {len(ranked):,}개 · 상위 10개 표시')
        cols={'name':'종목명','ticker':'종목코드','market':'시장','score':'기술 점수','return_5d_pct':'최근 5일(%)','return_20d_pct':'최근 20일(%)','asof_price':'가격 기준일'}
        if ranked.empty:
            st.info('조건에 맞는 최근 분석 종목이 없습니다. 시장·테마 조건을 넓히거나 아래 종목 상세 분석을 이용하세요.')
        else:
            st.dataframe(ranked.head(10).rename(columns=cols)[['종목명','종목코드','시장','추천 참고점수','기술 점수','가격 기준일']],hide_index=True,use_container_width=True, column_config={'추천 참고점수':explained_column('추천 참고점수',numeric=True),'기술 점수':explained_column('기술 점수',numeric=True)})
        with st.expander('🔎 추천 종목 분석', expanded=False):
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
                                     '매매 판단':explained_column('매매 판단',width='medium'),
                                     '분석 점수':st.column_config.NumberColumn('점수 /100 ⓘ',format='%.0f',help=glossary['기술 점수']),
                                     '현재가':st.column_config.NumberColumn('현재가',format='%.2f'),
                                     '1차 매수가':st.column_config.NumberColumn('매수 참고',format='%.2f'),
                                     '1차 목표가':st.column_config.NumberColumn('목표 참고',format='%.2f'),
                                     '손절 기준가':st.column_config.NumberColumn('손절 참고',format='%.2f'),
                                     '예상 상승폭':explained_column('예상 상승폭',numeric=True,fmt='%+.1f%%'),
                                     '예상 하락폭':explained_column('예상 하락폭',numeric=True,fmt='%.1f%%'),
                                     '손익비':explained_column('손익비',numeric=True,fmt='%.2f'),
                                     '가격 조건':explained_column('가격 조건',width='small'),
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
                            display_company_brief(st, name, ticker, f'batch_news_{i}')
                            with st.expander('전문 기술 지표 보기 · RSI / MACD 등'):
                                st.caption('RSI·MACD 등 지표별 설명은 표의 오른쪽 열에서 확인할 수 있습니다.')
                                indicators=indicator_explanations()
                                st.dataframe(pd.DataFrame([{'지표':k,'분석값':result.get(k),'쉬운 설명':d} for k,d in indicators]),
                                             hide_index=True,use_container_width=True,height=390,
                                             column_config={'지표':st.column_config.TextColumn(width='medium'),
                                                            '쉬운 설명':st.column_config.TextColumn(width='large')})
                    st.warning('매수·목표·손절 가격은 과거 차트로 계산한 참고 구간입니다. 실제 수익률 검증이나 미래 가격 예측이 아닙니다.')
                    with st.expander('📊 실제 추천 성과 검증 상태'):
                        st.info('실제 추천 성과는 아래 ‘지난 추천 성과 확인’에서 1·5·20거래일 관측 수익률과 통계 점검 결과를 확인하세요. 충분한 표본이 쌓이기 전에는 검증 부족으로 표시됩니다.')
                else:
                    st.info('상위 10종목의 상세 가격 구간과 지표를 보려면 위 분석 실행 버튼을 누르세요.')
        with st.expander('📊 지난 추천 성과 확인 (관측된 가격 기준)'):
            history_file=DATA/'recommendation_history.csv'
            if not history_file.exists():
                st.info('추천 기록이 아직 없습니다. 업데이트 후 GitHub Actions의 Market scan v9을 실행하면 기록이 시작됩니다.')
            else:
                try:
                    hist=pd.read_csv(history_file,dtype={'ticker':str})
                    if hist.empty:
                        st.info('기록된 추천이 없습니다.')
                    else:
                        hist['observed_return_pct']=pd.to_numeric(hist.get('observed_return_pct'),errors='coerce')
                        hist['elapsed_days']=pd.to_numeric(hist.get('elapsed_days'),errors='coerce')
                        done=hist.dropna(subset=['observed_return_pct','elapsed_days'])
                        a,b,c=st.columns(3)
                        a.metric('누적 추천 기록',f'{len(hist):,}건',help=glossary['누적 추천 기록'])
                        b.metric('이후 가격 확인',f'{len(done):,}건',help=glossary['이후 가격 확인'])
                        c.metric('관측 결과 평균',f"{done.observed_return_pct.mean():+.2f}%" if len(done) else '자료 없음',help=glossary['관측 결과 평균'])
                        st.caption('같은 종목이 여러 날짜·투자 기간에 중복 기록될 수 있습니다. 평균은 투자 수익률이나 전략 적중률이 아닙니다.')
                        with st.expander('❓ 위의 추천 건수·가격 확인·평균 수익률은 무엇을 뜻하나요? (쉬운 설명)', expanded=False):
                            st.markdown('''**① 누적 추천 기록:** 프로그램이 추천을 저장한 전체 횟수입니다. 같은 종목이 다른 날 또는 다른 투자 기간에 추천되면 각각 1건으로 셉니다.

**② 이후 가격 확인:** 일반 관측일·경과일·관측 수익률이 모두 저장되어 계산 가능한 기록 수입니다. 아래의 **1·5·20거래일별 확인 건수와는 다른 집계**입니다.

**③ 관측 결과 평균:** 위 ②의 기록들만 평균한 가격 변화율입니다. 2건만 확인됐다면 그 2건의 평균일 뿐이며 전체 추천 성과가 아닙니다.

**④ 1·5·20거래일 평균:** 추천 기준 종가와 각 거래일 뒤 종가를 비교합니다. 1거래일은 다음 *거래일*이고, 주말·휴장일은 건너뜁니다.

**⑤ 통계적 신뢰성 표:** 중복·이상 기록을 별도 기준으로 검토한 **유효 추천**만 사용합니다. 따라서 위의 96건이나 2건과 표의 숫자가 달라질 수 있습니다.

**주의:** 어느 수치도 실제 주문 체결, 거래비용, 손절 실행을 반영한 계좌 수익률이 아닙니다.''')
                        st.info('💡 보는 순서: 전체 추천 건수 → 1·5·20거래일 확인 건수 → 통계적 신뢰성 판정. 자료 부족이면 추천 전략이 검증됐다고 해석하지 마세요.')
                        display_hist = hist.sort_values('recorded_at_utc',ascending=False).head(100).copy()
                        display_hist['recorded_at_utc'] = display_hist['recorded_at_utc'].map(format_kst)
                        st.dataframe(display_hist.rename(columns={
                            'recorded_at_utc':'추천 기록 시각(한국시간)','period':'투자 기간','ticker':'종목코드',
                            'name':'종목명','entry_date':'추천 기준일','entry_close':'기준 종가',
                            'observed_date':'이후 관측일','observed_close':'이후 종가',
                            'elapsed_days':'경과 일수','observed_return_pct':'관측 수익률(%)'
                        })[['추천 기록 시각(한국시간)','투자 기간','종목명','종목코드','추천 기준일','기준 종가',
                             '이후 관측일','이후 종가','경과 일수','관측 수익률(%)']],
                            hide_index=True,use_container_width=True, column_config={k:explained_column(k) for k in ['투자 기간','종목명','종목코드','추천 기준일','기준 종가','이후 관측일','이후 종가','경과 일수','관측 수익률(%)']} | {'추천 기록 시각(한국시간)':st.column_config.TextColumn('추천 기록 시각(한국시간) ⓘ',help=glossary['추천 기록 시각'])})
                        st.markdown('**추천 이후 1·5·20거래일 성과 (확인된 자료만)**')
                        with st.expander('❓ 1·5·20거래일 성과는 어떻게 읽나요?', expanded=False):
                            st.markdown('''**예시:** 월요일 종가 10,000원에 추천된 종목이 화요일 종가 10,200원이라면 1거래일 가격 변화율은 +2%입니다. 그 다음 5번째 거래일 종가가 10,500원이면 5거래일 가격 변화율은 +5%입니다.

**예: 확인 70/96건:** 전체 추천 기록 96건 중 1거래일 뒤 종가를 확인한 기록이 70건이라는 뜻입니다. **미확인**은 실패나 손실을 뜻하지 않습니다.

**주의:** 아래의 1거래일 평균은 상단 '관측 결과 평균'과 집계에 사용하는 칸이 다르므로 숫자가 다를 수 있습니다.''')
                        for h in (1, 5, 20):
                            col=f'return_{h}d_pct'
                            if col not in hist.columns: hist[col]=float('nan')
                            hist[col]=pd.to_numeric(hist[col],errors='coerce')
                        horizon_cols=st.columns(3)
                        for ui,h in zip(horizon_cols,(1,5,20)):
                            observed=hist[f'return_{h}d_pct'].dropna()
                            ui.metric(f'{h}거래일 평균', f'{observed.mean():+.2f}%' if len(observed) else '미확인',
                                      help=f'관측 완료 {len(observed):,}건 / 전체 {len(hist):,}건. 추천 기준 종가 대비 이후 {h}번째 거래일 종가 변화')
                            ui.caption(f'확인 {len(observed):,}/{len(hist):,}건')
                        from statistical_validation import report as statistical_report
                        stats=statistical_report(history_file)
                        st.markdown('**통계적 신뢰성 점검**')
                        with st.expander('❓ 통계적 신뢰성 표의 숫자와 자료 부족 판정을 쉽게 이해하기', expanded=False):
                            st.markdown('''**유효 추천:** 중복·오류 등 검증 기준을 적용한 뒤 통계 계산에 사용할 수 있는 추천 건수입니다.

**관측 완료:** 유효 추천 중 해당 거래일의 이후 종가가 확보된 건수입니다.

**관측률:** 관측 완료 ÷ 유효 추천 × 100입니다. 예: 44 ÷ 64 = 68.75%, 화면에는 약 68.8%로 표시됩니다.

**서로 다른 추천일:** 추천한 날짜의 가짓수입니다. 같은 날 50종목을 추천해도 추천일은 1일입니다.

**서로 다른 종목:** 실제로 몇 종류의 종목을 평가했는지 보여줍니다.

**중앙값:** 결과를 작은 순서대로 정렬했을 때 가운데 값입니다. 극단적인 수익률의 영향을 평균보다 덜 받습니다.

**상승 비율:** 관측 종가가 추천 기준 종가보다 높았던 기록의 비율입니다. 실제 매매 승률이 아닙니다.

**95% 탐색구간:** 데이터가 충분할 때 평균의 불확실성을 살펴보는 통계 구간입니다. 미래 수익이 이 안에 들어간다는 보장이 아닙니다.

**자료 부족:** 현재 표본이나 날짜·종목의 다양성, 관측률이 검증 기준에 미달한 상태입니다. 수익성이 없다는 판정도, 수익성이 입증됐다는 판정도 아닙니다.''')
                        if stats['issues']:
                            st.error('데이터 검증 문제: ' + '; '.join(stats['issues'][:5]))
                        stat_rows=[]
                        for h, info in stats['horizons'].items():
                            stat_rows.append({'기간':f'{h}거래일','판정':info['status'],
                                '유효 추천':info.get('total',0),'관측 완료':info.get('observed',0),
                                '관측률(%)':info.get('coverage_pct',0),'서로 다른 추천일':info.get('days',0),
                                '서로 다른 종목':info.get('tickers',0),'평균 수익률(%)':info.get('mean_pct'),
                                '중앙값(%)':info.get('median_pct'),'상승 비율(%)':info.get('win_rate_pct'),
                                '95% 탐색구간 하한(%)':info.get('ci_low_pct'),
                                '95% 탐색구간 상한(%)':info.get('ci_high_pct')})
                        st.dataframe(pd.DataFrame(stat_rows),hide_index=True,use_container_width=True, column_config={k:explained_column(k) for k in ['기간','판정','유효 추천','관측 완료','관측률(%)','서로 다른 추천일','서로 다른 종목','평균 수익률(%)','중앙값(%)','상승 비율(%)']} | {'95% 탐색구간 하한(%)':st.column_config.NumberColumn('95% 하한 ⓘ',help=glossary['95% 하한']),'95% 탐색구간 상한(%)':st.column_config.NumberColumn('95% 상한 ⓘ',help=glossary['95% 상한'])})
                        st.caption('30건 이상·추천일 10일 이상·서로 다른 종목 10개 이상·관측률 70% 이상인 경우에만 날짜 단위 재표집으로 탐색적 95% 구간을 계산합니다. 추천 간 상관, 시장 국면, 거래비용, 데이터 누락 때문에 통계적 우위의 증명은 아닙니다.')
                        periods=[]
                        for period_name, group in hist.groupby('period',dropna=False):
                            item={'투자 기간':period_name,'추천 기록':len(group)}
                            for h in (1,5,20):
                                vals=group[f'return_{h}d_pct'].dropna()
                                item[f'{h}일 확인']=len(vals)
                                item[f'{h}일 평균(%)']=round(vals.mean(),2) if len(vals) else None
                            periods.append(item)
                        with st.expander('❓ 단기·스윙·중기·장기별 성과 표 읽는 법', expanded=False):
                            st.markdown('''**추천 기록:** 해당 기간으로 저장된 전체 추천 횟수입니다.

**1일·5일·20일 확인:** 각 거래일 뒤 종가를 확인한 기록 수입니다.

**1일·5일·20일 평균:** 해당 기간으로 추천된 종목의 각 관측 시점 평균 가격 변화율입니다.

**가상 예시:** 스윙 추천 22건 중 1일 확인 16건, 1일 평균 +1.26%라면, 16건의 다음 거래일 종가가 추천 기준 종가 대비 평균 1.26% 높았다는 뜻입니다. 22건 모두 수익을 냈다는 뜻은 아닙니다.''')
                        st.dataframe(pd.DataFrame(periods),hide_index=True,use_container_width=True, column_config={k:explained_column(k,numeric=k=='추천 기록') for k in ['투자 기간','추천 기록','1일 확인','1일 평균(%)','5일 확인','5일 평균(%)','20일 확인','20일 평균(%)']})
                        st.caption('거래일은 해당 종목 거래소의 실제 거래 세션 기준입니다. 거래 수수료·세금·슬리피지는 제외되며, 추천 기준 종가에 실제로 매수했다고 가정할 수 없습니다.')
                        st.warning('관측 가능한 추천만 평균에 포함되어 선택 편향이 있을 수 있습니다. 장중·장마감 시차, 데이터 누락 및 자동 수집 한계가 있으며, 미래 수익을 보장하거나 매매 적중률을 뜻하지 않습니다.')
                except (OSError,ValueError,KeyError) as exc:
                    st.warning(f'추천 기록 파일을 읽지 못했습니다: {exc}')
    with watchlist_tab:
        st.subheader('관심종목 통합 분석')
        st.caption('종목명 또는 종목코드로 검색하면 추천 참고점수와 기술 분석·매수/목표/손절 가격을 한 화면에서 확인할 수 있습니다.')
        st.info('💡 테마별 추천은 후보를 찾는 메뉴이고, 이곳은 특정 종목을 자세히 살펴보는 메뉴입니다. 추천 참고점수와 기술 점수는 계산 목적과 산식이 서로 다릅니다.')
        search_period=st.selectbox('분석할 투자 기간', PERIODS, index=1, key='unified_search_period',
            help='추천 참고점수는 선택한 투자 기간에 따라 달라집니다. 기술 점수는 가격 차트의 별도 규칙 기반 점수입니다.')
        symbol=st.text_input('종목명 또는 코드',placeholder='삼성전자 / 005930.KS / NVDA',key='simple_ticker')
        if st.button('🔎 선택 종목 통합 분석', type='primary', key='unified_analyze'):
            if not symbol.strip():
                st.warning('종목명이나 코드를 입력해 주세요.')
            else:
                ticker=resolve_symbol(symbol)
                # A single technical-report function is used for both recommendation details
                # and individual analysis, preventing duplicate or divergent price scenarios.
                result=cached_report(ticker)
                st.session_state['unified_report']={'ticker':ticker,'report':result,'period':search_period}
        stored=st.session_state.get('unified_report',{})
        if stored and symbol.strip() and stored.get('ticker')==resolve_symbol(symbol):
            result=stored.get('report',{})
            ticker=stored['ticker']
            if not isinstance(result,dict) or result.get('error'):
                st.warning(result.get('error','분석 결과를 불러오지 못했습니다.') if isinstance(result,dict) else '분석 결과 형식이 올바르지 않습니다.')
            else:
                if stored.get('period')!=search_period:
                    st.caption('투자 기간이 변경되었습니다. 추천 참고점수는 새 기간으로 계산되며 기술 분석 가격은 기존 조회 결과를 사용합니다.')
                st.success(f"{result.get('조회 티커',ticker)} · {result.get('종합 의견','관찰')} · 기술 분석 점수 {result.get('종합 점수(100)','-')}점/100점")
                matching=fresh[fresh['ticker'].fillna('').astype(str).str.upper().eq(ticker.upper())]
                if not matching.empty:
                    latest=matching.sort_values('scanned_at_utc').iloc[-1]
                    ranked_one=rank(matching,search_period).iloc[0]
                    st.markdown('**① 저장된 자동 분석 결과와 추천 참고점수**')
                    m1,m2,m3=st.columns(3)
                    m1.metric('추천 참고점수',f"{ranked_one['추천 참고점수']:.1f}",help=glossary['추천 참고점수'])
                    m2.metric('저장된 기술 점수',f"{float(latest['score']):.1f}" if pd.notna(latest.get('score')) else '미확인',help='자동 배치가 저장한 기술 점수입니다. 아래 실시간 요청 기술 점수와 기준 시점·산식이 달라질 수 있습니다.')
                    m3.metric('가격 기준일',str(latest.get('asof_price','-')))
                    st.caption('추천 참고점수는 저장된 자동 분석의 기간별 순위용 점수입니다. 아래 상세 기술 점수와 동일한 숫자가 아닙니다. 기준일·계산식이 다를 수 있습니다.')
                else:
                    st.info('최근 7일 저장된 자동 분석 결과에 이 종목이 없어 추천 참고점수는 표시하지 않습니다. 아래 개별 기술 분석은 계속 확인할 수 있습니다.')
                st.markdown('**② 종목별 기술 분석과 매매 판단**')
                st.write(f"기술 분석 점수 **{result.get('종합 점수(100)','-')}점 / 100점** · 분석 기준일 **{result.get('기준일','-')}** · 통화 **{result.get('통화','-')}**")
                keys=['기준 종가','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가']
                descriptions=['분석에 사용한 마지막 종가(실시간 시세 아님)','첫 번째 매수 검토 가격','두 번째 매수 검토 가격','첫 번째 목표 검토 가격','두 번째 목표 검토 가격','손실을 제한하기 위해 참고할 가격']
                st.dataframe(pd.DataFrame([{'항목':k,'가격':result.get(k),'쉬운 설명':d} for k,d in zip(keys,descriptions)]),hide_index=True,use_container_width=True)
                def number(key):
                    try:
                        v=float(result.get(key))
                        return v if pd.notna(v) else None
                    except (TypeError,ValueError): return None
                buy,target,stop=number('1차 매수 관찰가'),number('1차 목표 관찰가'),number('손실 제한 참고가')
                st.markdown('**③ 매수 가격 기준 예상 손익 비교**')
                if valid_scenario(buy,target,stop):
                    up=(target/buy-1)*100
                    down=(1-stop/buy)*100
                    a,b,c=st.columns(3)
                    a.metric('예상 상승폭',f'+{up:.1f}%',help=glossary['예상 상승폭'])
                    b.metric('예상 하락폭',f'-{down:.1f}%',help=glossary['예상 하락폭'])
                    c.metric('손익비',f'{up/down:.2f}:1',help=glossary['손익비'])
                else:
                    st.warning('손절가 < 1차 매수가 < 1차 목표가 조건이 맞지 않거나 가격이 없어 손익비를 계산하지 않았습니다.')
                with st.expander('📘 기술 지표 및 점수의 쉬운 설명',expanded=False):
                    indicators=indicator_explanations()
                    st.dataframe(pd.DataFrame([{'지표':k,'분석값':result.get(k),'쉬운 설명':d} for k,d in indicators]),hide_index=True,use_container_width=True)
                display_company_brief(st, symbol.strip(), ticker, 'watchlist_news')
                st.warning('점수는 미래 상승 확률이 아니며, 매수·목표·손절 가격은 참고 시나리오입니다. 주문 전에 실제 시세와 거래 위험을 확인하세요.')
    with news_tab:
        st.subheader('오늘의 증시 핵심 브리핑')
        st.caption('반복 기사를 주제별로 묶어 핵심 흐름·가능한 시장 영향·확인할 점을 정리합니다. 기사 제목을 근거로 한 잠정 분석이며 투자 신호가 아닙니다.')
        news_scope=st.radio('보고 싶은 정보', ['시장 전체 이슈','관심종목 관련 뉴스'],horizontal=True,key='news_scope')
        if news_scope=='시장 전체 이슈':
            display_briefing(st,MACRO_QUERY,'macro_news',limit=25)
        else:
            news_symbol=st.text_input('종목명 또는 코드',placeholder='삼성전자 / 005930.KS / NVDA',key='news_ticker')
            if news_symbol.strip():
                display_company_brief(st,news_symbol,resolve_symbol(news_symbol),'market_news_ticker')
            else:
                st.info('관심 종목을 입력하면 중요 공시 조회 가능 여부와 관련 뉴스의 핵심 흐름을 보여줍니다.')
        st.caption('국내 공시는 DART_API_KEY로 원문 주요 문장을 발췌하고, 미국 공시는 SEC_USER_AGENT 설정 시 제출 서식·날짜를 조회합니다. 원문을 검증한 투자 결론이나 실시간 매매 신호는 아닙니다.')
        with st.expander('❓ 뉴스·공시를 어떻게 투자 판단에 활용하나요?'):
            st.markdown('''**뉴스:** 언론이 보도한 사실과 전망을 구분하세요. 같은 뉴스가 여러 매체에 실려도 독립적인 호재 여러 개는 아닙니다.

**공시:** 기업이 공식적으로 제출한 문서입니다. 실적·유상증자·대규모 계약 등은 원문과 발표일을 확인하세요.

**예시:** '대규모 계약 체결' 기사가 있어도 매출액 대비 계약 규모와 계약 기간이 작으면 실제 영향은 제한적일 수 있습니다.

**주의:** 뉴스가 긍정적이어도 이미 주가에 반영됐을 수 있습니다. 기술지표, 손절 위험, 실제 시세와 함께 판단하세요.''')
    with st.expander('⚙️ 운영 상태 · 분석 범위와 점수 설명'):
        st.write(f"마지막 자동 분석 (한국시간): {format_kst(state.get('updated_utc'))}")
        st.caption('UTC는 세계 표준시이며 한국시간은 UTC보다 9시간 빠릅니다. 예: 00:00 UTC → 같은 날 오전 9시 (한국시간). 이 시각은 자동 분석 결과 저장 시각으로, 주식시장의 실시간 가격 갱신 시각은 아닙니다.')
        st.write(f"검색 가능한 종목 목록: {state.get('catalog_size',0):,}개 · 최근 조회 시도: {state.get('attempted',0):,}개")
        st.write(f"최근 조회 실패: {state.get('failed',0):,}개 · 누적 저장 결과: {len(scores):,}개")
        st.caption('목록 등록, 분석 성공, 최근 데이터 확보는 서로 다른 개념입니다. 현재 점수는 과거 가격 지표의 규칙 기반 평가이며 성과 검증과 별도입니다.')
        if 'market' in scores:
            st.dataframe(scores.groupby('market').size().rename('누적 저장 종목').reset_index(),hide_index=True,use_container_width=True)
        st.caption('안정적 표본 1,200종목 운영은 차기 배치 개선 대상입니다. 현 배치는 전체 종목 목록을 시장별로 순환 조회합니다.')
