"""Historical technical-analysis scenarios; not forecasts or live execution signals."""
import math
import pandas as pd


def analyze_history(frame, currency='KRW'):
    if frame is None or frame.empty or not {'High','Low','Close','Volume'}.issubset(frame.columns):
        raise ValueError('가격·거래량 데이터가 부족합니다.')
    d=frame[['High','Low','Close','Volume']].copy().apply(pd.to_numeric,errors='coerce').dropna(subset=['High','Low','Close'])
    d=d[(d.Close>0)&(d.High>=d.Low)]
    if len(d)<65:
        raise ValueError('60일 이동평균선 계산을 위해 최소 65거래일 데이터가 필요합니다.')
    c=d.Close; h=d.High; l=d.Low; v=d.Volume.fillna(0)
    ma5=float(c.tail(5).mean()); ma20=float(c.tail(20).mean()); ma60=float(c.tail(60).mean()); close=float(c.iloc[-1]); prev=float(c.iloc[-2]);
    delta=c.diff(); up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    den=float(down.iloc[-1]); num=float(up.iloc[-1]); rsi=100 if den==0 and num>0 else (50 if den==0 else 100-100/(1+num/den))
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); signal=macd.ewm(span=9,adjust=False).mean(); hist=float(macd.iloc[-1]-signal.iloc[-1]); prev_hist=float(macd.iloc[-2]-signal.iloc[-2]);
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1); atr=float(tr.rolling(14).mean().iloc[-1]);
    vol20=float(v.tail(20).mean()); vol_ratio=float(v.iloc[-1]/vol20) if vol20>0 else None
    # Exclude today's candle to avoid treating the current close as a historical support/resistance pivot.
    support=float(l.iloc[-21:-1].min()); resistance=float(h.iloc[-21:-1].max());
    trend=(10 if close>ma5 else 0)+(10 if close>ma20 else 0)+(10 if ma20>ma60 else 0)
    timing=(10 if 40<=rsi<=65 else 5 if 30<=rsi<40 or 65<rsi<=70 else 0)+(10 if hist>0 else 0)+(5 if hist>prev_hist else 0)
    volume=(10 if vol_ratio is not None and vol_ratio>=1.2 and close>=prev else 5 if vol_ratio is not None and vol_ratio>=0.8 else 0)+(10 if close>=prev else 0)
    risk=(10 if close>=support else 0)+(10 if atr/close<=0.04 else 5 if atr/close<=0.07 else 0)+(5 if rsi<70 else 0)
    score=trend+timing+volume+risk
    if score>=75: opinion='매수 조건 우세 (추격 매수 주의)'
    elif score>=60: opinion='분할 매수 검토'
    elif score>=40: opinion='관망·조건 확인'
    else: opinion='위험 관리 우선'
    # Illustrative levels only; resistance may be below last close after a breakout.
    entry1=min(ma20,close-0.5*atr); entry2=min(support,entry1-0.5*atr)
    stop=min(support-0.5*atr,entry2-0.5*atr)
    target1=max(resistance,close+atr); target2=max(target1+atr,close+2*atr)
    return {'기준일':str(d.index[-1].date()) if hasattr(d.index[-1],'date') else str(d.index[-1]),'통화':currency,'기준 종가':close,
            '5일선':ma5,'20일선':ma20,'60일선':ma60,'RSI(14)':round(rsi,1),'MACD 히스토그램':round(hist,4),
            '거래량/20일 평균':round(vol_ratio,2) if vol_ratio is not None else None,'ATR(14)':round(atr,2),
            '최근 20일 지지 후보':support,'최근 20일 저항 후보':resistance,
            '추세 점수(30)':trend,'진입 시점 점수(25)':timing,'거래량 점수(20)':volume,'위험 관리 점수(25)':risk,
            '종합 점수(100)':score,'종합 의견':opinion,
            '1차 매수 관찰가':round(entry1,2),'2차 매수 관찰가':round(entry2,2),
            '1차 목표 관찰가':round(target1,2),'2차 목표 관찰가':round(target2,2),'손실 제한 참고가':round(stop,2),
            '기준가 대비 손절 거리(%)':round((close-stop)/close*100,2)}


def get_technical_report(ticker):
    try:
        import yfinance as yf
        for symbol in [ticker]+([ticker[:-3]+('.KQ' if ticker.endswith('.KS') else '.KS')] if ticker.endswith(('.KS','.KQ')) else []):
            try:
                data=yf.Ticker(symbol).history(period='9mo',interval='1d',auto_adjust=False,timeout=12)
                report=analyze_history(data,'KRW' if symbol.endswith(('.KS','.KQ')) else 'USD')
                report['조회 티커']=symbol
                report['데이터 공급원']='Yahoo Finance · 일별 OHLCV (지연 가능)'
                return report
            except (ValueError,KeyError,TypeError,IndexError):
                continue
            except Exception:
                continue
        return {'error':'충분한 일별 시세를 확보하지 못했습니다. 종목 코드·공급원·상장 기간을 확인하세요.'}
    except ImportError:
        return {'error':'yfinance 모듈을 사용할 수 없습니다.'}
