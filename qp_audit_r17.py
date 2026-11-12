"""R17: descriptive out-of-sample monitoring of saved scheduled recommendations.
No simulated fills, no invented missing returns, no strategy performance claims.
"""
from collections import defaultdict
import math
import pandas as pd

HORIZONS=(1,5,20)

def observations(records, group):
    rows=[]
    for rec in records:
        slot=rec.get('slot','')
        group_rows=rec.get('groups',{}).get(group,[])
        entry=rec.get('entry_review',{}).get(group,{}).get('rows',[])
        timing={str(r.get('티커')):r for r in entry}
        for item in group_rows:
            ticker=str(item.get('ticker',''))
            outcome=rec.get('outcomes',{}).get(ticker,{})
            review=timing.get(ticker,{})
            row={'회차':slot,'종목':item.get('name',ticker),'티커':ticker,
                 '추천순위':item.get('rank'),'매수타이밍점수':review.get('점수'),
                 '타이밍판단':review.get('판단','기록 없음'),
                 '평가기준일':outcome.get('base_date'),'평가기준가':outcome.get('base')}
            for h in HORIZONS:
                v=pd.to_numeric(outcome.get(str(h)),errors='coerce')
                row[f'{h}일 수익률']=float(v) if pd.notna(v) and math.isfinite(float(v)) else None
            rows.append(row)
    return pd.DataFrame(rows)

def summarize(df, horizon, group_col=None):
    col=f'{horizon}일 수익률'
    if df.empty or col not in df: return pd.DataFrame()
    groups=[('전체',df)] if group_col is None else list(df.groupby(group_col,dropna=False))
    output=[]
    for key,subset in groups:
        values=pd.to_numeric(subset[col],errors='coerce').dropna()
        n=len(values)
        # Every repeated ticker-slot observation remains visible; not independent trades.
        output.append({'구분':str(key),'추천 건수':len(subset),'검증 완료':n,
                       '검증률(%)':round(n/len(subset)*100,1) if len(subset) else None,
                       '평균 수익률(%)':round(float(values.mean()),2) if n else None,
                       '중앙값(%)':round(float(values.median()),2) if n else None,
                       '상승 비율(%)':round(float((values>0).mean()*100),1) if n else None,
                       '최저 수익률(%)':round(float(values.min()),2) if n else None})
    return pd.DataFrame(output)

def diagnostics(records,group):
    relevant=[r for r in records if group in r.get('groups',{})]
    rows=observations(records,group)
    return {'회차':len(relevant),'추천건수':len(rows),
            '매수타이밍판단확보':int((rows['타이밍판단']!='기록 없음').sum()) if not rows.empty else 0,
            '기준가확보':int(pd.to_numeric(rows['평가기준가'],errors='coerce').notna().sum()) if not rows.empty else 0}

def show(st,records,group):
    st.subheader('6. R17 추천 신뢰도 점검')
    st.caption('실제 주문 성과가 아닌, 저장된 정기 추천 이후 확정 종가 변화에 대한 관찰 통계입니다. 매수 타이밍 점수는 사후 성과로 학습하거나 조정하지 않습니다.')
    d=observations(records,group); info=diagnostics(records,group)
    c=st.columns(3)
    c[0].metric('정기 추천 회차',info['회차'])
    c[1].metric('추천 기록 건수',info['추천건수'])
    c[2].metric('타이밍 판단 연결 건수',info['매수타이밍판단확보'])
    if d.empty:
        st.info('정기 예약 추천 기록이 없습니다. 첫 예약 실행 후 기록이 쌓이고, 이후 거래일이 경과해야 성과를 확인할 수 있습니다.')
        return
    horizon=st.selectbox('검증 기간',[1,5,20],format_func=lambda n:f'{n}거래일',key='qp_r17_horizon')
    total=summarize(d,horizon)
    st.markdown('**전체 추천 성과(관찰 기준)**')
    st.dataframe(total,hide_index=True,use_container_width=True)
    if int(total.iloc[0]['검증 완료'])==0:
        st.info('수익률 수치가 비어 있는 이유: 추천 이후 첫 거래일의 확정 종가를 평가 기준가로 삼고, 그 다음부터 선택한 1·5·20거래일이 지나야 관측값을 계산합니다. 예약/수동 실행 직후에는 0건이 정상일 수 있습니다. GitHub Actions에서 추적 작업이 실행되고 데이터 파일이 저장되는지도 확인하세요.')
    with st.expander('추천 신뢰도 점검: 숫자와 계산 기준을 쉽게 설명'):
        st.markdown('''**추천 회차**: 프로그램이 추천 목록을 저장한 실행 횟수입니다. **추천 건수**: 그 회차에 저장한 종목의 합계로, 중복 종목도 포함합니다. **타이밍 판단 연결**: 추천 당시 RSI·MACD 등을 계산해 매수 검토/관망 등을 함께 저장한 건수입니다. 0이면 해당 시점의 판단 기록이 없었다는 뜻이지 모두 매수 실패했다는 뜻이 아닙니다.

**검증 완료**: 추천 이후 미래 가격을 충분히 관측하여 수익률 계산을 마친 건수입니다. **검증률**: 검증 완료 ÷ 추천 건수 × 100입니다. **평균 수익률**: 검증된 관측 수익률의 산술평균이며, **상승 비율**은 검증된 건 중 수익률이 0%보다 큰 비율입니다.

**예시**: 10건을 추천하고 3건만 1일 관측이 끝났으며 수익률이 +2%, -1%, +3%라면 검증률은 30%, 평균 수익률은 약 +1.33%, 상승 비율은 66.7%입니다. 아직 관측하지 못한 7건은 0% 수익으로 처리하지 않습니다.

**중요**: 기준가는 추천 당시 10시·15시 실시간 체결가가 아닌 **추천 후 첫 거래일 확정 수정종가**입니다. 실제 매수 가능성과 수수료·세금·손절·익절은 포함되지 않습니다. 표본이 적거나 반복 추천이 많으면 신뢰도를 판단할 수 없습니다.''')
    if int(total.iloc[0]['검증 완료'])<30:
        st.warning('검증 완료 표본이 30건 미만입니다. 통계적 신뢰도가 부족하므로 전략 우열을 판단하지 마세요.')
    st.markdown('**매수 타이밍 판단별 성과 비교**')
    st.dataframe(summarize(d,horizon,'타이밍판단'),hide_index=True,use_container_width=True)
    st.markdown('**추천 순위 구간별 비교**')
    d=d.copy()
    d['순위 구간']=pd.cut(pd.to_numeric(d['추천순위'],errors='coerce'),bins=[0,3,5,10],labels=['1~3위','4~5위','6~10위'])
    st.dataframe(summarize(d,horizon,'순위 구간'),hide_index=True,use_container_width=True)
    with st.expander('개별 검증 원자료 및 해석 주의사항'):
        st.dataframe(d,hide_index=True,use_container_width=True)
        st.markdown('''- **미검증 건은 0% 수익으로 계산하지 않습니다.** 검증률을 반드시 함께 보세요.
- **동일 종목의 오전·오후 반복 추천은 독립 거래가 아닙니다.** 표본 수가 많아도 독립적인 예측 사례가 적을 수 있습니다.
- **기준가는 추천 후 첫 거래일의 확정 수정종가**입니다. 실제 매수 체결가, 추천 당시 가격 또는 10시·15시 체결가가 아닙니다.
- **손절·익절·분할 매수·수수료·세금·슬리피지·환율은 미반영**입니다. 따라서 실제 주문 전략의 백테스트나 승률이 아닙니다.
- **타이밍 판단이 없는 과거 기록은 '기록 없음'으로 유지**합니다. 과거에 존재하지 않았던 점수를 사후 생성하지 않습니다.
- **미국/한국 시장의 거래일 및 데이터 제공 지연**으로 동일 시각에 평가가 완료되지 않을 수 있습니다.''')
