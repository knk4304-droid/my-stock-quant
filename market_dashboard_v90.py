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
    with st.expander('🌐 전체 시장 자동 탐색 · 추천 후보와 분석 진행 상황 (v9.4)',expanded=True):
        state,scores=read_snapshot()
        if not state:
            st.info('아직 자동 배치 분석 결과가 없습니다. GitHub Actions에서 Market scan v9을 1회 실행하세요.')
            return
        a,b,c,d=st.columns(4)
        a.metric('검색 가능한 전체 종목',f"{state.get('catalog_size',0):,}개")
        b.metric('최근 실행에서 조회한 종목',f"{state.get('attempted',0):,}개")
        c.metric('최근 실행에서 분석 완료',f"{state.get('succeeded',0):,}개")
        d.metric('지금까지 분석한 고유 종목',f'{len(scores):,}개')
        st.caption('전체 목록에 등록된 종목과 실제 분석 완료 종목은 다릅니다. 순차 분석하며, 점수는 과거 시세 기반 참고 지표이지 상승 확률이 아닙니다.')
        total=int(state.get('catalog_size',0) or 0)
        if total: st.progress(min(1.0,len(scores)/total),text=f'전체 목록 대비 누적 분석 기록: {len(scores):,}/{total:,}종목 ({len(scores)/total:.1%}) · 기록에 오래된 종목이 포함될 수 있음')
        with st.expander('ℹ️ 이 숫자와 추천 점수는 무슨 뜻인가요?',expanded=False):
            st.markdown('**검색 가능한 전체 종목**은 확보한 종목코드 목록입니다. **최근 실행에서 조회한 종목**은 한 번의 자동 작업에서 조회를 시도한 수입니다. **분석 완료**는 가격 자료가 충분하여 점수를 계산한 수입니다. **지금까지 분석한 고유 종목**은 이전 실행 결과까지 합친 저장 수이며 최신 시세라는 뜻은 아닙니다.\n\n**추천 점수**는 추세·수익률·변동성에 따른 규칙 점수입니다. 실제 수익률이나 매수 성공 확률이 아닙니다.')
        st.caption(f"이번 작업: 신규 순환 조회 {state.get('rotation_count',state.get('attempted',0)):,}개 · 이전 후보 재확인 {state.get('revisit_count',0):,}개 · 실패 {state.get('failed',0):,}개")
        st.caption(f"마지막 자동 분석(UTC): {state.get('updated_utc','미확인')}")
        if not scores.empty:
            summary=scores.groupby('market',dropna=False).size().rename('누적 분석 저장').reset_index().rename(columns={'market':'시장'})
            catalog_counts=state.get('catalog_by_market',{})
            if not catalog_counts:
                catalog_file=DATA/'catalog.csv'
                if catalog_file.exists():
                    catalog_counts=pd.read_csv(catalog_file,usecols=['market']).market.value_counts().to_dict()
            summary['등록 종목']=summary['시장'].map(catalog_counts).fillna(0).astype(int)
            for m, count in catalog_counts.items():
                if m not in summary['시장'].values:
                    summary=pd.concat([summary,pd.DataFrame([{'시장':m,'누적 분석 저장':0,'등록 종목':count}])],ignore_index=True)
            summary=summary.sort_values('시장')
            st.markdown('**시장별 실제 분석 현황**')
            st.dataframe(summary,hide_index=True,use_container_width=True)
            if not any(str(m).startswith(('KOSPI','KOSDAQ','KR ETF')) for m in catalog_counts):
                st.warning('국내 주식·ETF 종목 목록이 아직 확보되지 않았습니다. 국내 시장까지 분석했다고 볼 수 없습니다. 자동 분석 작업의 KR LIST WARNING 로그를 확인하세요.')
            st.caption('등록 종목은 검색 가능한 목록, 누적 분석 저장은 가격을 조회하여 점수가 저장된 종목입니다. 전체 시장 선택 시 저장된 결과만 표시됩니다.')
        if scores.empty: return
        scores=scores.copy()
        scores['score']=pd.to_numeric(scores['score'],errors='coerce')
        scores['scanned_at_utc']=pd.to_datetime(scores['scanned_at_utc'],utc=True,errors='coerce')
        age=(pd.Timestamp.now(tz='UTC')-scores['scanned_at_utc']).dt.total_seconds()/86400
        st.markdown('### 추천 후보 찾아보기')
        st.info('이 표는 전체 상장종목을 동시에 평가한 결과가 아니라, 지금까지 시세 분석이 완료되어 저장된 종목의 후보 순위입니다. 실제 매수 신호가 아닙니다.')
        market_coverage=scores.groupby('market',dropna=False).size().to_dict()
        available=set(str(k) for k in market_coverage)
        expected={'KOSPI','KOSDAQ','KR ETF','NASDAQ','NYSE/OTHER'}
        missing=sorted(expected-available)
        if missing: st.warning('분석 결과가 없는 시장: '+', '.join(missing)+' · 전체 시장을 충분히 분석한 것으로 해석하지 마세요.')
        st.caption('기본 설정은 전체 시장·주식과 ETF 모두·최근 30일 분석입니다. 아래 목록은 자동 분석을 마친 종목 중 조건에 맞는 후보만 보여줍니다.')
        c_market,c_period=st.columns(2)
        with c_market:
            market_options=['전체']+sorted(scores.market.dropna().astype(str).unique().tolist())
            market=st.selectbox('어느 시장을 볼까요?',market_options,key='v90_market',help='전체는 분석이 완료된 모든 시장을 합쳐 보여줍니다. 등록만 된 종목은 포함되지 않습니다.')
        with c_period:
            horizon=st.selectbox('투자 기간', ['종합','단기 (1~3일)','스윙 (1~2주)','중기 (1~3개월)','장기 (1년 이상)'],key='v92_horizon',help='투자 기간에 따라 과거 가격 지표의 비중을 다르게 적용합니다. 미래 수익률 예측은 아닙니다.')
        q=st.text_input('종목 찾기 (선택)',key='v90_query',placeholder='예: 삼성전자, 005930, AAPL')
        with st.expander('⚙️ 상세 검색 조건 (필요할 때만 변경)',expanded=False):
            max_age=st.selectbox('분석 기록 기간',['7일','30일','전체'],index=1,key='v90_age',help='7일·30일은 해당 기간에 분석한 기록만 표시합니다. 전체에는 오래된 기록도 포함될 수 있습니다.')
            asset_label=st.selectbox('종목 종류',['모두 보기','주식만','ETF만'],key='v94_asset_label')
            min_score=st.slider('최소 기술 평가 점수',0,100,60,5,key='v91_score',help='이 점수보다 낮은 종목을 제외합니다. 60점은 기본 검색 기준일 뿐 매수 적합 판정이 아닙니다.')
            st.caption('기술 평가 점수는 과거 가격의 추세·수익률·변동성으로 계산한 규칙 점수이며 매수 성공 확률이 아닙니다.')
        if max_age!='전체': scores=scores.loc[age.le(7 if max_age=='7일' else 30)].copy()
        if market!='전체': scores=scores[scores.market.eq(market)]
        asset={'모두 보기':'전체','주식만':'STOCK','ETF만':'ETF'}[asset_label]
        if asset!='전체': scores=scores[scores.asset_type.eq(asset)]
        if q: scores=scores[scores['name'].astype(str).str.contains(q,case=False,regex=False)|scores['ticker'].astype(str).str.contains(q,case=False,regex=False)]
        # Simple horizon-specific ranking using only observed historical features.
        # These are ranking heuristics, not validated expected returns.
        for key in ['return_5d_pct','return_20d_pct','volatility_annual']:
            scores[key]=pd.to_numeric(scores.get(key),errors='coerce')
        r5=scores['return_5d_pct'].clip(-25,25).fillna(0)
        r20=scores['return_20d_pct'].clip(-40,40).fillna(0)
        vol=scores['volatility_annual'].clip(0,3).fillna(1)
        base=scores['score'].fillna(0)
        if horizon.startswith('단기'): rank_score=base*.5+r5*.8-vol*12
        elif horizon.startswith('스윙'): rank_score=base*.6+r5*.35+r20*.25-vol*10
        elif horizon.startswith('중기'): rank_score=base*.7+r20*.35-vol*10
        elif horizon.startswith('장기'): rank_score=base*.8+r20*.15-vol*18
        else: rank_score=base
        scores['관점별 참고점수']=rank_score.round(2)
        ranked=scores.sort_values(['관점별 참고점수','score'],ascending=[False,False])
        ranked=ranked.loc[ranked['score'].ge(min_score)]
        display=ranked.head(30).rename(columns={'ticker':'종목코드','name':'종목명','market':'시장','asset_type':'유형','close':'기준 종가','score':'기술 점수','return_5d_pct':'최근 5거래일 수익률(%)','return_20d_pct':'최근 20거래일 수익률(%)','volatility_annual':'연율 변동성','asof_price':'가격 기준일','scanned_at_utc':'분석 저장 시각(UTC)'})
        st.markdown(f'**조건에 맞는 후보: {len(ranked):,}개** · 점수순 상위 30개')
        if not ranked.empty:
            ranked_markets=ranked['market'].fillna('미분류').astype(str).value_counts()
            st.caption('후보 시장별 분포: '+ ' · '.join(f'{k} {v:,}개' for k,v in ranked_markets.items()))
            if len(ranked_markets)==1 and market=='전체':
                st.warning('현재 필터를 통과한 후보는 한 시장에만 있습니다. 다른 시장이 분석되지 않았거나 점수·기간 조건에서 제외되었을 수 있습니다.')
        if ranked.empty: st.info('현재 조건에 맞는 종목이 없습니다. 상세 검색 조건에서 기간을 전체로 변경하거나 최소 점수를 낮춰 보세요.')
        preferred=['종목코드','종목명','시장','유형','기준 종가','기술 점수','관점별 참고점수','가격 기준일','분석 저장 시각(UTC)']
        st.dataframe(display[[c for c in preferred if c in display.columns]],hide_index=True,use_container_width=True)
        with st.expander('📋 상세 수익률·변동성 데이터',expanded=False):
            st.dataframe(display,hide_index=True,use_container_width=True)
        st.caption('관점별 참고점수는 기간에 따라 과거 수익률·변동성 가중치를 달리한 임시 규칙입니다. **검증된 예측값이 아닙니다.**')
        st.caption('이 목록은 조건을 충족한 **관찰 후보**이며 매수 확정 신호가 아닙니다. 상세 매수·매도 전략은 아래 종목 검색에서 추가 확인하세요.')
        st.caption(f'기간·시장·유형·검색 적용 후 {len(scores):,}개 · 점수 조건 통과 {len(ranked):,}개 · 최대 30개 표시. 기존 정밀 종합점수와 직접 비교하지 마세요.')
        with st.expander('📈 이후 가격 관측 기록 · 추천 검증 준비',expanded=False):
            obs=DATA/'observations.csv'
            if obs.exists():
                try:
                    history=pd.read_csv(obs)
                    if history.empty: st.info('아직 이전 분석 이후 다시 조회된 종목이 없습니다.')
                    else:
                        st.dataframe(history.tail(100).iloc[::-1],hide_index=True,use_container_width=True)
                        st.caption('같은 종목을 나중에 다시 분석했을 때의 가격 변화입니다. 추천 수익률, 고정 보유기간 백테스트 또는 실제 거래 성과는 아닙니다.')
                        if 'observed_return_pct' in history:
                            values=pd.to_numeric(history['observed_return_pct'],errors='coerce').dropna()
                            if len(values):
                                a,b,c=st.columns(3)
                                a.metric('재조회 관측 건수',f'{len(values):,}건')
                                b.metric('관측 상승 비율',f'{(values.gt(0).mean()*100):.1f}%')
                                c.metric('관측 평균 가격 변화',f'{values.mean():+.2f}%')
                                st.warning('관측 간격이 일정하지 않고 추천 시점의 거래 조건도 반영되지 않았습니다. 승률 또는 투자 성과로 해석할 수 없습니다.')
                except Exception as exc: st.warning(f'관측 기록을 읽을 수 없습니다: {exc}')
            else: st.info('분석한 종목을 이후에 다시 조회하면 관측 기록이 쌓입니다. 현재는 검증 성과가 충분하지 않습니다.')
        st.download_button('📥 분석 결과 CSV 다운로드',scores.to_csv(index=False).encode('utf-8-sig'),file_name='market_scan_v90.csv',mime='text/csv',key='v90_csv')
