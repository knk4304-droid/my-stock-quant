"""R21 unified recommendation ranking and detailed report, opt-in daily quote lookup."""
import pandas as pd
from ranking_options import rank_candidates, SORT_OPTIONS
from technical_report_v63 import get_technical_report

PERIODS={'단기 1~3일':'1~3D','스윙 1~2주':'1~2W','중기 1~3개월':'1~3M','장기 1년 이상':'1Y+'}
SORTS={'종합점수순':SORT_OPTIONS[0], '현재매수유망순':SORT_OPTIONS[1]}

def filtered_candidates(df, period, market, theme, classifier):
    data=df.drop_duplicates(subset=['티커']).copy()
    if market=='국내':data=data[data['티커'].astype(str).str.endswith(('.KS','.KQ'))]
    if market=='미국':data=data[~data['티커'].astype(str).str.endswith(('.KS','.KQ'))]
    if theme!='전체':
        data=data[data.apply(lambda r: ('ETF' in str(classifier(r.get('티커',''),r.get('종목명',''))).upper()) == (theme=='ETF'),axis=1)]
    key='총점_'+PERIODS[period]
    if key not in data:return pd.DataFrame()
    data['총점']=pd.to_numeric(data[key],errors='coerce')
    return data

def explain(report, total, buy_strength, signal):
    rsi=report.get('RSI(14)'); hist=report.get('MACD 히스토그램'); ratio=report.get('거래량/20일 평균')
    lines=[f'**종합 판단:** 투자 매력도 {total:.1f}/100점, 매수 신호 강도 {buy_strength}/100점. 두 점수는 상승 확률이 아닙니다.']
    if isinstance(rsi,(int,float)):
        lines.append(f'**과열·모멘텀:** RSI {rsi:.1f}로 '+('70 이상 과열 가능성이 있어 추격매수에 주의해야 합니다.' if rsi>=70 else '30 미만 과매도 구간이지만 반등은 보장되지 않습니다.' if rsi<30 else '극단적인 과열·과매도 구간은 아닙니다.'))
    if isinstance(hist,(int,float)):lines.append(f'**추세 변화:** MACD 히스토그램 {hist:+.4f}로 '+('양의 모멘텀이지만 지속 여부를 확인해야 합니다.' if hist>0 else '모멘텀이 약하므로 반전 확인이 필요합니다.'))
    if isinstance(ratio,(int,float)):lines.append(f'**거래량:** 20일 평균의 {ratio:.2f}배입니다. '+('평균보다 거래가 활발합니다.' if ratio>=1.2 else '거래량 확증이 강하지 않습니다.'))
    lines.append(f'**매수 판단:** {signal}. 지지·저항과 위험 한도를 확인하고 가격이 급등했으면 진입을 보류합니다.')
    return '\n\n'.join(lines)

def show_unified_recommendations(st, df, macro, engine, buy_fn, sell_fn, classifier, risk_notice, features):
    st.markdown('### 3. 추천종목 TOP10')
    st.caption('현재 분석 가능한 종목에서 조건별 TOP10을 선정합니다. 자동 저장된 전체 시장 3,900여 종목을 전부 새로 조회하는 기능은 아닙니다.')
    a,b,c,d=st.columns(4)
    with a:period=st.selectbox('투자기간',list(PERIODS),index=1,key='r21_period')
    with b:market=st.selectbox('시장',['전체','국내','미국'],key='r21_market')
    with c:theme=st.selectbox('테마 / 상품유형',['전체','주식','ETF'],key='r21_theme',help='현재 저장 자료에 검증된 산업 테마 분류가 없어 우선 주식/ETF 필터를 제공합니다.')
    with d:sort_label=st.selectbox('정렬 기준',list(SORTS),key='r21_sort')
    if st.button('🔍 검색 추천종목 TOP10',type='primary',key='r21_search'):
        st.session_state['r21_active']=(period,market,theme,sort_label)
    active=st.session_state.get('r21_active')
    if not active:
        st.info('조건을 선택하고 「검색 추천종목 TOP10」 버튼을 누르세요.');return
    if active!=(period,market,theme,sort_label):
        st.info('선택 조건이 변경되었습니다. 검색 버튼을 다시 눌러 결과를 갱신하세요.');return
    pool=filtered_candidates(df,period,market,theme,classifier)
    if pool.empty:st.warning('해당 조건에 분석 가능한 종목이 없습니다.');return
    strengths=[]
    for _,r in pool.iterrows():
        try:strengths.append(buy_fn(r,macro)[0])
        except Exception:strengths.append(None)
    pool['매수 신호 강도']=strengths
    ranked=rank_candidates(pool,SORTS[sort_label],limit=10)
    if ranked.empty:st.warning('유효한 점수와 가격 자료가 부족합니다.');return
    ranked=ranked.reset_index(drop=True)
    ranked.insert(0,'순위',range(1,len(ranked)+1))
    ranked['상품유형']=[classifier(r.get('티커',''),r.get('종목명','')) for _,r in ranked.iterrows()]
    st.caption(f'분석 가능 후보 {len(pool)}개 중 {len(ranked)}개 · 정렬: {sort_label} · 가격은 마지막 수집 일봉 기준(실시간 체결가 아님)')
    columns=['순위','종목명','티커','시장','상품유형','총점','매수 신호 강도','당일 수익률','1주 수익률','차트링크']
    st.dataframe(ranked[[k for k in columns if k in ranked]],hide_index=True,use_container_width=True,
                 column_config={'차트링크':st.column_config.LinkColumn('차트 보기',display_text='차트 열기')})
    st.caption('종합점수순은 투자 매력도, 현재매수유망순은 기존 분석 데이터의 매수 조건을 우선합니다. 후자는 실시간 호가 순위가 아닙니다.')
    st.markdown('### 4. 추천종목 상세분석')
    st.caption('두 상세분석 메뉴를 하나로 통합했습니다. 선택한 종목의 점수·지표·매수/매도 의견을 한곳에서 확인합니다.')
    tickers=ranked['티커'].astype(str).tolist()
    ticker=st.selectbox('상세분석 종목 선택',tickers,format_func=lambda t:f"{ranked.loc[ranked['티커'].astype(str)==t,'순위'].iloc[0]}위 · {ranked.loc[ranked['티커'].astype(str)==t,'종목명'].iloc[0]} ({t})",key='r21_detail')
    row=ranked.loc[ranked['티커'].astype(str)==ticker].iloc[0]
    strength,signal,buy_text=buy_fn(row,macro)
    sell_signal,sell_reason,action,target,stop,_=sell_fn(row)
    st.markdown(f"#### {row['종목명']} ({ticker})")
    st.dataframe(pd.DataFrame([{'항목':'종합점수','수치':f"{row['총점']:.1f}/100",'의미':'가격·거래량 기반 투자 매력도'},
                              {'항목':'매수 신호 강도','수치':f'{strength}/100','의미':'내부 규칙 신호, 상승 확률 아님'},
                              {'항목':'최근 1주 등락률','수치':f"{float(row['r_1w_val']):+.2f}%",'의미':'과열·급락 여부 참고'},
                              {'항목':'매수 판단','수치':signal,'의미':buy_text},
                              {'항목':'매도 판단','수치':sell_signal,'의미':sell_reason},
                              {'항목':'가정 목표 범위','수치':target,'의미':'실제 목표가 예측 아님'},
                              {'항목':'가정 손실 범위','수치':stop,'의미':'실제 주문 손절가 아님'}]),hide_index=True,use_container_width=True)
    with st.expander('기존 10대 평가 요소 수치',expanded=False):
        st.dataframe(pd.DataFrame([{'평가항목':k,'점수':row.get(k,'자료 없음')} for k in features]),hide_index=True,use_container_width=True)
    st.info(f'**매수 관점:** {buy_text}\n\n**매도·보유 관점:** {sell_reason} {action}')
    st.caption(risk_notice(row['상품유형']))
    if st.button('📊 선택 종목 최신 일봉·RSI·MACD·매매 기준 조회',key='r21_technical_btn'):
        with st.spinner('선택 종목의 최근 일별 가격·기술지표를 조회합니다.'):
            st.session_state['r21_technical']=(ticker,get_technical_report(ticker))
    stored=st.session_state.get('r21_technical')
    if stored and stored[0]==ticker:
        report=stored[1]
        if 'error' in report:st.warning(report['error'])
        else:
            st.caption(f"가격 기준일 {report.get('기준일')} · {report.get('데이터 공급원')} · 실시간 체결가 아님")
            keys=['기준 종가','5일선','20일선','60일선','RSI(14)','MACD 히스토그램','거래량/20일 평균','ATR(14)','최근 20일 지지 후보','최근 20일 저항 후보','1차 매수 관찰가','2차 매수 관찰가','1차 목표 관찰가','2차 목표 관찰가','손실 제한 참고가','종합 점수(100)']
            st.dataframe(pd.DataFrame([{'분석 항목':k,'수치':report.get(k,'자료 없음')} for k in keys]),hide_index=True,use_container_width=True)
            st.markdown(explain(report,float(row['총점']),strength,signal))
            st.warning('매수가·목표가·손절가는 과거 일봉 기반 참고 시나리오입니다. 실시간 호가·뉴스·공시·수수료·슬리피지는 별도 확인해야 합니다.')
