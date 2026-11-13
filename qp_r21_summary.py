"""Readable highlights from actual daily-bar technical report."""
def summarize(r):
    lines=[]
    def val(k):
        try:return float(r[k])
        except (KeyError,TypeError,ValueError):return None
    rsi=val('RSI(14)'); macd=val('MACD 히스토그램'); vol=val('거래량/20일 평균'); close=val('기준 종가'); ma=val('20일선')
    if rsi is not None:lines.append(f"**RSI {rsi:.1f}:** "+('과열 가능성이 있어 추격매수에 주의해야 합니다.' if rsi>=70 else '과매도 구간으로 추가 하락 위험을 확인해야 합니다.' if rsi<30 else '극단적 과열·과매도는 아닙니다.'))
    if macd is not None:lines.append(f"**MACD 히스토그램 {macd:+.4f}:** "+('상승 모멘텀이 있지만 단독 매수 근거는 아닙니다.' if macd>0 else '모멘텀 회복 여부를 확인해야 합니다.'))
    if vol is not None:lines.append(f"**거래량 {vol:.2f}배:** "+('평균 대비 거래가 활발합니다.' if vol>=1.2 else '거래량 증가가 충분히 확인되지 않았습니다.'))
    if close is not None and ma is not None:lines.append(f"**20일선 {ma:,.2f}:** 기준 종가 {close:,.2f}는 20일선 "+('위에 있습니다.' if close>ma else '아래에 있습니다.'))
    lines.append('**최종 확인:** 1·2차 매수 관찰가와 목표가·손절가의 손익비를 확인하고, 실제 주문 전 시세·뉴스·공시를 별도 확인하세요.')
    return '\n\n'.join(lines)
