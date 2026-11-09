"""Read-only display of scheduled market scans; no automatic network calls."""
from pathlib import Path
import json
import pandas as pd

DATA=Path(__file__).resolve().parent/'market_scan_data'

def read_snapshot():
    state_path=DATA/'state.json'; scores_path=DATA/'scores.csv'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    scores=pd.read_csv(scores_path,dtype={'ticker':str}) if scores_path.exists() else pd.DataFrame()
    return state,scores

def show(st):
    with st.expander('🌐 전체 시장 순차 자동 분석 · 저장된 최신 결과 (v9.0)',expanded=True):
        state,scores=read_snapshot()
        if not state:
            st.info('아직 자동 배치 분석 결과가 없습니다. GitHub Actions에서 Market scan v9을 1회 실행하세요.')
            return
        a,b,c,d=st.columns(4)
        a.metric('발견한 전체 종목',f"{state.get('catalog_size',0):,}개")
        b.metric('최근 배치 분석 시도',f"{state.get('attempted',0):,}개")
        c.metric('최근 배치 분석 성공',f"{state.get('succeeded',0):,}개")
        d.metric('누적 결과 저장',f'{len(scores):,}개')
        st.caption(f"최근 배치 실행(UTC): {state.get('updated_utc','미확인')} · 모든 종목을 한 번에 분석한 결과가 아닙니다. 과거 데이터 기반 기술적 점수이며 예측 확률이 아닙니다.")
        if scores.empty: return
        scores=scores.copy()
        scores['score']=pd.to_numeric(scores['score'],errors='coerce')
        scores['scanned_at_utc']=pd.to_datetime(scores['scanned_at_utc'],utc=True,errors='coerce')
        age=(pd.Timestamp.now(tz='UTC')-scores['scanned_at_utc']).dt.total_seconds()/86400
        max_age=st.selectbox('최근 분석 결과만 보기',['7일','30일','전체'],index=1,key='v90_age')
        if max_age!='전체': scores=scores.loc[age.le(7 if max_age=='7일' else 30)].copy()
        market=st.selectbox('시장 구분',['전체']+sorted(scores.market.dropna().unique().tolist()),key='v90_market')
        if market!='전체': scores=scores[scores.market.eq(market)]
        asset=st.selectbox('상품 유형',['전체','STOCK','ETF'],key='v90_asset')
        if asset!='전체': scores=scores[scores.asset_type.eq(asset)]
        q=st.text_input('종목명 또는 티커 검색',key='v90_query')
        if q: scores=scores[scores['name'].astype(str).str.contains(q,case=False,regex=False)|scores['ticker'].astype(str).str.contains(q,case=False,regex=False)]
        st.dataframe(scores.sort_values('score',ascending=False).head(100),hide_index=True,use_container_width=True)
        st.caption(f'조건에 맞는 분석 결과 {len(scores):,}개 · 상위 100개 표시. 점수는 단순 기술지표 기반이며 기존 정밀 종합점수와 직접 비교할 수 없습니다.')
        st.download_button('📥 분석 결과 CSV 다운로드',scores.to_csv(index=False).encode('utf-8-sig'),file_name='market_scan_v90.csv',mime='text/csv',key='v90_csv')
