"""Compact authenticated admin landing; legacy tools remain opt-in."""
from pathlib import Path
import json
import pandas as pd
DATA=Path(__file__).resolve().parent/'market_scan_data'

def show(st):
    st.header('관리자 · 분석 운영센터')
    mode=st.radio('관리 목적',['분석 현황','저장 종목 조회','검증 기록','기존 고급 도구'],horizontal=True,key='qp_admin_r14')
    try:
        state=json.loads((DATA/'state.json').read_text())
        d=pd.read_csv(DATA/'scores.csv',dtype={'ticker':str})
        d['_time']=pd.to_datetime(d.scanned_at_utc,utc=True,errors='coerce')
        d=d.sort_values('_time').drop_duplicates('ticker',keep='last')
    except Exception as e:
        st.warning('저장 데이터 확인 필요: '+type(e).__name__); return mode
    if mode=='분석 현황':
        fresh=d[(pd.Timestamp.now(tz='UTC')-d['_time']).dt.total_seconds().between(0,604800)]
        total=int(state.get('catalog_size',0) or 0); attempted=int(state.get('attempted',0) or 0); success=int(state.get('succeeded',0) or 0)
        for c,(label,value) in zip(st.columns(4),[('등록 종목',total),('누적 분석',len(d)),('최근 7일',len(fresh)),('최근 실행 성공',f'{success}/{attempted}')]):c.metric(label,value)
        st.markdown('**읽는 법:** 등록 15,896개 중 3,302개가 저장됐다면 누적 범위는 약 20.8%입니다. 최근 실행 254/275는 시세 분석 성공률 92.4%이며 추천 적중률이 아닙니다. 최근 7일 수는 현재 추천 후보의 최대 범위입니다.')
        if total:st.progress(min(1,len(d)/total))
        updated=pd.to_datetime(state.get('updated_utc'),utc=True,errors='coerce');st.caption('최근 자동 실행(KST): '+(updated.tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M') if pd.notna(updated) else '미확인'))
        summary=pd.concat([d.groupby('market').size().rename('누적 분석'),fresh.groupby('market').size().rename('최근 7일'),pd.Series(state.get('catalog_by_market',{}),dtype=float).rename('등록')],axis=1).fillna(0).astype(int)
        st.dataframe(summary,use_container_width=True)
        with st.expander('시세 수집 실패 확인'):
            p=DATA/'last_failures.csv'
            if p.exists():st.dataframe(pd.read_csv(p),hide_index=True,use_container_width=True)
            else:st.info('실패 기록 파일 없음')
    elif mode=='저장 종목 조회':
        q=st.text_input('종목명 또는 코드',key='qp_admin_search'); market=st.selectbox('시장',['전체']+sorted(d.market.dropna().unique().tolist()),key='qp_admin_market')
        if market!='전체':d=d[d.market.eq(market)]
        if q:d=d[d.name.fillna('').str.contains(q,case=False,regex=False)|d.ticker.str.contains(q,case=False,regex=False)]
        st.caption(f'{len(d):,}개 · 저장 가격이며 실시간 호가가 아닙니다. 최신 개별 분석은 관심종목 검색에서 실행하세요.')
        d['저장 시각(KST)']=d['_time'].dt.tz_convert('Asia/Seoul').dt.strftime('%Y-%m-%d %H:%M')
        view=d[['ticker','name','market','close','score','asof_price','저장 시각(KST)']].rename(columns={'ticker':'코드','name':'종목','market':'시장','close':'저장 가격','score':'기술점수','asof_price':'가격 기준일'})
        st.dataframe(view.head(300),hide_index=True,use_container_width=True);st.download_button('전체 검색 결과 CSV',view.to_csv(index=False).encode('utf-8-sig'),'qp_saved.csv')
    elif mode=='검증 기록':
        from qp_home_r12 import legacy_validation
        from qp_weekly import load
        from ranking_history import PERIODS
        st.metric('정기 추천 저장 회차',len(load()));st.caption('정기 기록은 추천 화면 5번에서 조건별로 확인합니다. 아래는 이전 전체시장 검증 기록입니다.')
        legacy_validation(st,st.selectbox('투자 기간',PERIODS,key='qp_admin_period'))
    else:
        st.info('이전 버전의 개별 종합 리포트, 주문 수량 계산, CSV 확장 분석 등을 보존했습니다. 이 메뉴를 선택할 때만 기존 분석을 실행합니다. 대표 48개·865개 자료는 전체시장 자동 분석과 별개입니다.')
    return mode
