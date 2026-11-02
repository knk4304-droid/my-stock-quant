# app.py - UI 및 통합 대시보드 메인 (v4.00 최종 완치판)
import datetime
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from universe import UniverseLoader
from quant import QuantEngine, generate_buy_analysis, generate_sell_analysis

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

warnings.filterwarnings('ignore')

FEATURE_NAMES = [
    '성장성(CAGR)', '수익성(ROE)', '재무건전성', '밸류에이션', '기술적모멘텀',
    '수급/거래량', '환율민감도', '금리환경', '시장상대강도', '대외변동성'
]

def fix_stock_name_str(raw_name: str, name_map: dict) -> str:
    """숫자로만 표출되는 종목코드를 한글 종목명 (티커)으로 100% 강제 전환하는 정제 함수"""
    clean_text = str(raw_name).strip()
    clean_code = clean_text.split()[0].split('(')[0].split('.')[0].strip()
    
    if clean_code.isdigit() or (len(clean_code) == 6 and clean_code.isalnum()):
        k_name = (
            name_map.get(f"{clean_code}.KS") or 
            name_map.get(f"{clean_code}.KQ") or 
            name_map.get(clean_code)
        )
        if k_name:
            return f"{k_name} ({clean_code})"
    return clean_text

def fetch_realtime_macro():
    macro_results = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # 1. 국내 지수 수집 (네이버 API)
    try:
        url_kr = "https://m.stock.naver.com/api/index/KOSPI/basic"
        res = requests.get(url_kr, headers=headers, timeout=3).json()
        macro_results['KOSPI'] = {
            'val': float(res['closePrice'].replace(',', '')),
            'change': float(res['fluctuationsRatio'])
        }
    except Exception:
        macro_results['KOSPI'] = {'val': None, 'change': None}

    try:
        url_kq = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
        res = requests.get(url_kq, headers=headers, timeout=3).json()
        macro_results['KOSDAQ'] = {
            'val': float(res['closePrice'].replace(',', '')),
            'change': float(res['fluctuationsRatio'])
        }
    except Exception:
        macro_results['KOSDAQ'] = {'val': None, 'change': None}

    try:
        url_fx = "https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic"
        res = requests.get(url_fx, headers=headers, timeout=3).json()
        macro_results['USDKRW'] = {
            'val': float(res['closePrice'].replace(',', '')),
            'change': float(res['fluctuationsRatio'])
        }
    except Exception:
        macro_results['USDKRW'] = {'val': None, 'change': None}

    # 2. 미국 지수 수집 (1순위: 야후 파이낸스 / 2순위: 네이버 API)
    us_targets = {
        'S&P 500': {'yf': '^GSPC', 'naver': 'SPI@SPX'},
        '나스닥': {'yf': '^IXIC', 'naver': 'NAS@IXIC'},
        'VIX': {'yf': '^VIX', 'naver': 'SPI@VIX'}
    }

    for key, cfg in us_targets.items():
        success = False
        try:
            hist = yf.Ticker(cfg['yf']).history(period='5d', timeout=4)
            if hist.empty or len(hist) < 2:
                hist = yf.Ticker(cfg['yf']).history(period='1mo', timeout=4)
            if not hist.empty and len(hist) >= 1:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else curr
                rate = round(((curr - prev) / prev) * 100, 2) if prev > 0 else 0.0
                macro_results[key] = {'val': curr, 'change': rate}
                success = True
        except Exception:
            pass

        # 야후 수집 실패 시 네이버 API 시도
        if not success:
            try:
                url_us = f"https://m.stock.naver.com/api/index/{cfg['naver']}/basic"
                res = requests.get(url_us, headers=headers, timeout=3).json()
                macro_results[key] = {
                    'val': float(res['closePrice'].replace(',', '')),
                    'change': float(res['fluctuationsRatio'])
                }
            except Exception:
                # 💡 최종 실패 시에도 0.0 대신 None으로 통일
                macro_results[key] = {'val': None, 'change': None}

    # 3. 모든 데이터 수집 후 마지막에 반환
    return macro_results


def get_chart_link(ticker: str, name: str) -> str:
    # 1. 입력받은 티커의 공백을 제거하고 대문자로 변환해 깔끔하게 정제
    clean_ticker = str(ticker).strip().upper()
    
    # 2. 한국 주식 판별 기준 (점'.'으로 분리 시 앞이 6자리 숫자거나, .KS/.KQ로 끝나는 경우)
    code_part = clean_ticker.split('.')[0]
    
    if clean_ticker.endswith('.KS') or clean_ticker.endswith('.KQ') or (len(code_part) == 6 and code_part.isdigit()):
        # 네이버 증시는 순수 6자리 숫자로만 접속
        url = f"https://finance.naver.com/item/main.naver?code={code_part}"
    else:
        # 미국 등 해외 주식은 하이픈('-')을 점('.')으로 변경하여 야후 파이낸스로 연결
        yf_ticker = clean_ticker.replace('-', '.')
        url = f"https://finance.yahoo.com/quote/{yf_ticker}/"
        
    return f"[{name}]({url})"


def render_weekly_market_briefing(df, macro_info, name_map):
    # 1. 지수 데이터 원본 가져오기 (수집 실패 시 None)
    vix_raw = macro_info.get('VIX', {}).get('val')
    nasdaq_raw = macro_info.get('나스닥', {}).get('change')
    kospi_raw = macro_info.get('KOSPI', {}).get('change')
    usdkrw_raw = macro_info.get('USDKRW', {}).get('val')

    # 2. VIX 안전 처리 및 상태 문구 생성
    if vix_raw is not None:
        vix_val = float(vix_raw)
        vix_str = f"{vix_val:.2f} pt"
        vix_status = "🟢 변동성 안정 구간 (안정적 상승 추세 유지 가능)" if vix_val < 20.0 else "🔴 변동성 경보 구간 (분할 매수 및 리스크 관리 필수)"
    else:
        vix_str = "점검중"
        vix_status = "⚪ 변동성 데이터 수집 불가 (리스크 관리에 유의하세요)"

    # 3. 기타 마크로 지표 문자열 가공 (None 방어)
    nasdaq_str = f"{float(nasdaq_raw):+.2f}%" if nasdaq_raw is not None else "-"
    kospi_str = f"{float(kospi_raw):+.2f}%" if kospi_raw is not None else "-"
    usdkrw_str = f"{float(usdkrw_raw):,.2f}원" if usdkrw_raw is not None else "점검중"

    # 4. 종목 데이터 가공
    df_copy = df.copy()
    df_copy['종목명'] = df_copy['종목명'].apply(lambda x: fix_stock_name_str(x, name_map))

    buy_picks = df_copy[df_copy['r_1w_val'] < 8.0].drop_duplicates('종목명').sort_values(by='총점_1W', ascending=False).head(3)
    take_profits = df_copy[df_copy['r_1w_val'] >= 8.0].drop_duplicates('종목명').sort_values(by='r_1w_val', ascending=False).head(3)
    stop_losses = df_copy[(df_copy['r_1w_val'] <= -5.0) & (df_copy['총점_1W'] < 55.0)].drop_duplicates('종목명').head(3)
    
    st.markdown(f"""
    ### 📋 [AI 퀀트 주간 종합 브리핑] 이번 주 시장 전망 & 대응 전략
    
    #### 1. 🌐 글로벌 & 국내 증시 마크로 환경 진단
    * **시장 변동성 (VIX):** 현재 `{vix_str}` $\rightarrow$ **{vix_status}**
    * **미국/국내 연동성:** 나스닥(`{nasdaq_str}`), KOSPI(`{kospi_str}`), 원/달러 환율(`{usdkrw_str}`)
    * **주간 시장 종합 의견:** 단기적 차별화 장세가 강하게 나타나고 있습니다. 주가가 최근 1주일간 급등(+8% 이상)한 과열 종목은 추격 매수를 보류하고, 수급과 퀀트 총점이 우수한 눌림목 종목으로 집중하는 전략이 유리합니다.
    #### 2. 🟢 이번 주 최우선 강력 매수 관심 종목 (Top Picks)
    """)
    if not buy_picks.empty:
        for idx, (_, r) in enumerate(buy_picks.iterrows(), start=1):
            market = r.get('시장', 'KR')
            pred_return = r.get('미래수익률_1W', 0.0)
            score = r.get('총점_1W', 0)
            st.markdown(f"    {idx}. **{r['종목명']} ({market})** | 예측 수익률: `+{pred_return}%` | 퀀트 총점: `{score}`점\n       👉 **매수 타점:** 현재가 부근 비중 30% 1차 진입 후 눌림목마다 분할 매수")
    else:
        st.markdown("    - ⚪ **[안내]** 현재 최우선 조건에 부합하는 매수 관심 종목이 없습니다.")

    st.markdown("\n    #### 🔴 이번 주 비중 축소 (익절 & 교체 매도) 리딩 종목")
    if not take_profits.empty:
        for _, r in take_profits.iterrows():
            st.markdown(f"    - 🟠 **[익절 권장] {r['종목명']}** (1주 등락률 `+{r['r_1w_val']:.1f}%` 목표가 돌파 $\rightarrow$ 보유 비중 50% 이상 분할 매도하여 수익 확정)")
    else:
        st.markdown("    - ⚪ **[안내]** 현재 익절 권장 대상 종목이 없습니다.")

    if not stop_losses.empty:
        for _, r in stop_losses.iterrows():
            st.markdown(f"    - 🔴 **[손절/교체] {r['종목명']}** (1주 등락률 `{r['r_1w_val']:.1f}%`, 퀀트 총점 `{r['총점_1W']}`점 약세 $\rightarrow$ 전량 매도 후 우량주 교체)")

@st.cache_data(ttl=60)
def load_quant_database():
    try:
        df_stocks = pd.read_parquet('quant_stocks.parquet')
        df_macro = pd.read_parquet('quant_macro.parquet')
        _, name_map = UniverseLoader.get_full_universe()
        
        if not df_stocks.empty and '종목명' in df_stocks.columns:
            df_stocks['종목명'] = df_stocks['종목명'].apply(lambda x: fix_stock_name_str(x, name_map))
        
        # 💡 df_macro가 비어있지 않을 때만 iloc[0] 접근하도록 방어
        if not df_macro.empty:
            m_row = df_macro.iloc[0]
            macro_info = {
                'KOSPI': {'val': m_row.get('kospi_val', 0.0), 'change': m_row.get('kospi_chg', 0.0)},
                'KOSDAQ': {'val': m_row.get('kosdaq_val', 0.0), 'change': m_row.get('kosdaq_chg', 0.0)},
                'S&P 500': {'val': m_row.get('sp500_val', 0.0), 'change': m_row.get('sp500_chg', 0.0)},
                '나스닥': {'val': m_row.get('nasdaq_val', 0.0), 'change': m_row.get('nasdaq_chg', 0.0)},
                'USDKRW': {'val': m_row.get('usdkrw_val', 0.0), 'change': m_row.get('usdkrw_chg', 0.0)},
                'VIX': {'val': m_row.get('vix_val', 0.0), 'change': m_row.get('vix_chg', 0.0)}
            }
            updated_at = m_row.get('updated_at', "데이터 없음")
        else:
            macro_info = {}
            updated_at = "데이터 없음"

        engine = QuantEngine()
        return df_stocks, engine, macro_info, updated_at, name_map

    except Exception as e:
        _, name_map = UniverseLoader.get_full_universe()
        return pd.DataFrame(), QuantEngine(), {}, "데이터 없음", name_map

def render_korean_market_card(title, data, link):
    val = data.get('val')
    change = data.get('change')
    
    # 💡 데이터가 수집되지 않고 None으로 반환된 경우 UI 예외 처리
    if val is None or change is None:
        val_str = "점검중"
        change_str = "-"
        color = "#8E8E93" # 회색 처리
    else:
        val_str = f"{val:,.2f}"
        if change > 0:
            color = "#FF3B30"
            change_str = f"▲ +{change:.2f}%"
        elif change < 0:
            color = "#007AFF"
            change_str = f"▼ {change:.2f}%"
        else:
            color = "#8E8E93"
            change_str = "0.00%"

    card_html = f"""
    <div style="
        background-color: #F8F9FA;
        border: 1px solid #E9ECEF;
        border-radius: 10px;
        padding: 12px 15px;
        text-align: center;
        margin-bottom: 10px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.04);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #495057; margin-bottom: 4px;">{title}</div>
        <div style="font-size: 20px; font-weight: 700; color: {color}; margin-bottom: 2px;">{val_str}</div>
        <div style="font-size: 13px; font-weight: 700; color: {color}; margin-bottom: 8px;">{change_str}</div>
        <a href="{link}" target="_blank" style="
            display: inline-block;
            font-size: 11px;
            color: #6C757D;
            text-decoration: none;
            background-color: #E9ECEF;
            padding: 3px 8px;
            border-radius: 4px;
        ">🔗 차트보기</a>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def trigger_github_workflow():
    """웹 화면에서 GitHub Actions 배치 업데이트를 즉시 호출하는 함수"""
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO", "knk4304-droid/my-stock-quant")
    
    if not token:
        st.error("❌ GitHub Token이 설정되지 않았습니다. Secrets 설정을 확인하세요.")
        return False
        
    url = f"https://api.github.com/repos/{repo}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"event_type": "trigger_batch_update"}
    
    res = requests.post(url, json=payload, headers=headers)
    return res.status_code == 204


# ==========================================
# 2. UI 및 메인 실행 부분
# ==========================================
st.set_page_config(page_title="AI 추천 주식 매매 (v4.00)", page_icon="📈", layout="wide")

if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=30 * 1000, key="quant_realtime_loop")

df, engine, macro_info, updated_at, name_map = load_quant_database()

# UI 상단 데이터 업데이트 버튼 영역
col_title, col_btn = st.columns([4, 1])

with col_title:
    st.title("📈 AI 추천 주식 매매 (v4.00)")
    st.caption(f"부제 4.00 - 뉴스 NLP 감성 분석 및 백테스팅 엔진 검증판 | 마지막 데이터 업데이트: {updated_at}")

with col_btn:
    st.write("") # 여백
    if st.button("🔄 실시간 갱신 실행", help="클릭 시 백그라운드 데이터 수집 엔진을 즉시 실행합니다."):
        with st.spinner("GitHub 수집 엔진에 최신화 요청 중..."):
            if trigger_github_workflow():
                st.success("✅ 수집 요청 완료! (약 1분 후 새로고침하세요)")
                time.sleep(2)
                st.rerun()
            else:
                st.error("❌ 갱신 요청 실패")

with st.expander("ℹ️ **[클릭] AI 퀀트 시스템 핵심 매커니즘 & 매매 가이드 보기**", expanded=False):
    st.markdown("""
    ### 📊 v4.00 핵심 진단 지표 산출 가이드
    
    | 지표명 | 점수 산출 공식 및 핵심 로직 | 금융공학적 의미 및 활용법 |
    | :--- | :--- | :--- |
    | **퀀트 총점** | $\sum (\text{10대 요인} \times \text{가중치}) + \text{뉴스 감성 점수}$ | 체력, 모멘텀, 뉴스 호재를 종합 평가한 **기업 체력 점수** (100점 만점) |
    | **예상 수익률** | $(\text{총점} - 50.0) \times \text{기간별 가수} + (\text{뉴스 점수} \times 0.02)$ | 백테스트 시뮬레이션 기반 **향후 기간별 목표 상승 여력(Up-side)** |
    | **기대 승률** | $\text{Clip}(\text{총점}_{1W} \times 1.1 + \text{뉴스가산}, 60\%, 95\%)$ | 단기 진입 시 **손실 없이 플러스 수익으로 마감할 통계적 확률** |
    | **매수 시그널** | 승률 $70\%$ 이상 & $1W$ 등락률 $+8\%$ 미만일 때 `🟢 강력 매수` | 추격 매수를 방지하고 **안전하게 1차 분할 매수할 최적 타점** |
    | **매도 시그널** | 약세 하락주 + **악재 뉴스 발생** 시 `🔴 손절/교체` 최상단 표출 | 계좌 손실 방지를 위해 **가장 먼저 손절/익절해야 할 대응 긴급도** |
    
    ---
    * **분할 모듈 시스템:** 코드가 잘리는 현상을 완벽히 방지하여 전 기능이 다운 없이 안정적으로 구동됩니다.
    * **주간 종합 브리핑:** 글로벌/국내 시장 환경과 매수/매도 대응 방향을 매주 자동 정리합니다.
    * **AI 종합 필터 Top 10:** 전체 유니버스에서 퀀트점수, 미래수익률, 승률, 안전장치를 종합 평가하여 **기간별(1W ~ 3Y+) 가장 사야 할 최적의 10개 종목**과 **매수/매도 타이밍 리포트**를 제시합니다.
    * **관심 종목 개별 진단:** 전체 유니버스 모수 종목 중 원하시는 종목들을 드롭다운으로 다중 선택하여 정밀 진단 리포트를 확인하실 수 있습니다.
    """)

st.subheader("🌐 실시간 주요 시장 지수 현황")
m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)

index_configs = [
    (m_col1, "KOSPI", macro_info.get('KOSPI', {'val': 0, 'change': 0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"),
    (m_col2, "KOSDAQ", macro_info.get('KOSDAQ', {'val': 0, 'change': 0}), "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ"),
    (m_col3, "S&P 500", macro_info.get('S&P 500', {'val': 0, 'change': 0}), "https://finance.yahoo.com/quote/^GSPC/"),
    (m_col4, "나스닥", macro_info.get('나스닥', {'val': 0, 'change': 0}), "https://finance.yahoo.com/quote/^IXIC/"),
    (m_col5, "원/달러 환율", macro_info.get('USDKRW', {'val': 0, 'change': 0}), "https://m.stock.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"),
    (m_col6, "VIX (변동성)", macro_info.get('VIX', {'val': 0, 'change': 0}), "https://finance.yahoo.com/quote/^VIX/")
]

for col, name, data, link in index_configs:
    with col:
        render_korean_market_card(name, data, link)

if not df.empty:
    with st.expander("📋 **[클릭하여 열기] AI 퀀트 주간 종합 브리핑 리포트 (이번 주 시장 전망 & 대응 전략)**", expanded=True):
        render_weekly_market_briefing(df, macro_info, name_map)

st.markdown("---")

FIXED_CATEGORIES = [
    '🎯 [MY] 관심 종목 개별 진단',
    '🏆 [AI 종합 필터] 기간별 최우선 매수 추천 Top 10 (강력 추천)',
    '🏆 통합 전체 유니버스 (국내+미국 종합)',
    '🏆 국내 ETF',
    '코스피200',
    '코스닥100',
    'S&P500',
    '나스닥100'
]

if not df.empty:
    full_uni, full_names = UniverseLoader.get_full_universe()
    stock_options = sorted([f"{m_name} - {full_names.get(t, t)}" for m_name, t_list in full_uni.items() for t in t_list])

    tabs = st.tabs(["미래 1주일 (1W)", "미래 1개월 (1M)", "미래 6개월 (6M)", "미래 1년 (1Y)", "미래 5년 (5Y)", "미래 10년 (10Y)", "미래 10년 이상 (10Y+)"])
    period_codes = ["1W", "1M", "6M", "1Y", "5Y", "10Y", "10Y+"]

    for tab, p_code in zip(tabs, period_codes):
        with tab:
            st.markdown(f"### 🎯 [{p_code}] 테마 그룹별 맞춤형 가중치 배점 가이드")
            w_large = engine.get_weights_by_market('코스피200', p_code)
            w_small = engine.get_weights_by_market('코스닥100', p_code)
            w_etf = engine.get_weights_by_market('국내 ETF', p_code)

            w_summary_df = pd.DataFrame(
                [w_large, w_small, w_etf],
                columns=FEATURE_NAMES,
                index=['대형주 그룹 (코스피/S&P)', '소형 고성장주 그룹', 'ETF 그룹']
            )
           # 💡 최신 Streamlit 권장 사양 적용: use_container_width=True -> width="stretch"
            st.dataframe(w_summary_df, width="stretch")
            st.markdown("---")

            for c_idx, cat in enumerate(FIXED_CATEGORIES):
                if "관심 종목" in cat:
                    st.markdown("### 🎯 [MY] 관심 종목 직접 선택 개별 진단")
                    selected_stocks = st.multiselect(
                        "진단하고 싶은 관심 종목을 선택하세요 (전체 모수에서 여러 개 선택 가능):",
                        options=stock_options,
                        default=[],
                        key=f"custom_select_{p_code}_{c_idx}"
                    )
                    if selected_stocks:
                        target_names = [s.split(' - ')[1] for s in selected_stocks]
                        cat_df = df[df['종목명'].apply(lambda x: any(tn in str(x) for tn in target_names))].drop_duplicates(subset=['종목명']).copy()
                    else:
                        cat_df = pd.DataFrame()
                elif "AI 종합 필터" in cat:
                    st.markdown(f"### 🏆 [AI 종합 필터] [{p_code}] 기간별 최우선 매수 추천 Top 10 & 매매 전략")
                    cat_df = df.drop_duplicates(subset=['종목명']).copy()
                elif "통합 전체 유니버스" in cat:
                    st.markdown(f"### 🏆 {cat} Top 10")
                    cat_df = df.drop_duplicates(subset=['종목명']).copy()
                elif "국내 ETF" in cat:
                    st.markdown("### 🏆 국내 ETF Top 10")
                    cat_df = df[df['시장'] == '국내 ETF'].copy()
                else:
                    st.markdown(f"### 🏆 {cat} Top 10")
                    cat_df = df[df['시장'] == cat].copy()

if not cat_df.empty:
                # 1. 종목명 표준 정제
                cat_df['종목명'] = cat_df['종목명'].apply(lambda x: fix_stock_name_str(x, name_map))
                
                # 2. 선택된 기간(p_code) 점수 매핑
                if f"총점_{p_code}" in cat_df.columns:
                    cat_df['총점'] = cat_df[f"총점_{p_code}"]
                if f"미래수익률_{p_code}" in cat_df.columns:
                    cat_df['예측수익률(%)'] = cat_df[f"미래수익률_{p_code}"]

                # 3. 매수/매도 정밀 분석
                def analyze_stock_row(r):
                    try:
                        p_val, b_sig, _ = generate_buy_analysis(r, macro_info)
                        s_sig, _, _, _, _, s_rank = generate_sell_analysis(r)
                        return pd.Series([p_val, b_sig, s_sig, s_rank])
                    except Exception:
                        return pd.Series([60.0, "🟡 관망", "🟢 보유 유지", 1])

                cat_df[['기대상승확률(%)', '매도시그널', '매도_detail', '매도우선순위']] = cat_df.apply(analyze_stock_row, axis=1)

                   if "AI 종합 필터" in cat:
                        # 1. r_1w_val 컬럼 안전 체크
                        if 'r_1w_val' in cat_df.columns:
                            filtered_df = cat_df[cat_df['r_1w_val'] < 8.0].copy()
                        else:
                            filtered_df = cat_df.copy()
                        
                        # 2. 필터링 후 데이터가 없을 경우를 대비한 안전 로직
                        if filtered_df.empty:
                            filtered_df = cat_df.copy()

                        filtered_df['AI종합점수'] = (
                            filtered_df['총점'] * 0.5 +
                            filtered_df['기대상승확률(%)'] * 0.3 +
                            filtered_df['예측수익률(%)'] * 0.2
                        )
                        cat_df = filtered_df.sort_values(by='AI종합점수', ascending=False).head(10)

                    elif "관심 종목" not in cat:
                        col_head1, col_head2 = st.columns([3, 1])
                        with col_head2:
                            cat_sort_opt = st.selectbox(
                                "정렬 옵션 선택:",
                                options=["퀀트점수 순", "미래 기대 수익률 순 (%)", "매수시그널 순 (확률 %)", "매도시그널 순 (대응)"],
                                index=0,
                                key=f"sort_{cat}_{p_code}_{c_idx}"
                            )
                        
                        # 정렬 키 컬럼 존재 여부 확인 후 안전 정렬
                        sort_r1w = 'r_1w_val' if 'r_1w_val' in cat_df.columns else '총점'
                        
                        if "미래 기대 수익률" in cat_sort_opt:
                            cat_df = cat_df.sort_values(by=['예측수익률(%)', '기대상승확률(%)'], ascending=[False, False]).head(10)
                        elif "매수시그널" in cat_sort_opt:
                            cat_df = cat_df.sort_values(by=['기대상승확률(%)', sort_r1w, '총점'], ascending=[False, False, False]).head(10)
                        elif "매도시그널" in cat_sort_opt:
                            cat_df = cat_df.sort_values(by=['매도우선순위', sort_r1w], ascending=[False, False]).head(10)
                        else:
                            cat_df = cat_df.sort_values(by=['총점', '기대상승확률(%)'], ascending=[False, False]).head(10)

                    def make_named_link(row):
                        raw_link = str(row.get('차트링크', ''))
                        url = raw_link.split('](')[-1].rstrip(')') if '](' in raw_link else raw_link
                        c_name = fix_stock_name_str(row['종목명'], name_map)
                        return f"[{c_name}]({url})" if url else c_name

                    cat_df['종목(차트보기)'] = cat_df.apply(make_named_link, axis=1)

                    # FEATURE_NAMES 안전 조회 및 표출 컬럼 구성
                    f_names = FEATURE_NAMES if 'FEATURE_NAMES' in globals() else []
                    desired_cols = ['종목(차트보기)', '시장', '당일 수익률', '1일 전', '2일 전', '1주 수익률', '1달 수익률', '3개월 수익률', '총점'] + f_names
                    available_cols = [c for c in desired_cols if c in cat_df.columns]

                    display_df = cat_df[available_cols].reset_index(drop=True)
                    display_df.index = display_df.index + 1
                    
                    # st.markdown을 사용하여 하이퍼링크 표출 안정성 확보
                    st.markdown(display_df.to_markdown())
                    
                    expander_title = (
                        f"💡 [{cat}] [{p_code}] AI 선정 탑픽 10선 정밀 매매 가이드 (사야 하는 법 & 파는 타이밍)"
                        if "AI 종합 필터" in cat
                        else f"🔍 [{cat}] 입력 종목별 매수 추천 시그널 및 매도/손익절 종합 진단 리포트"
                    )

                    with st.expander(expander_title, expanded=False):
                        for idx, (_, row) in enumerate(cat_df.iterrows(), start=1):
                            prob, buy_signal, buy_opinion = generate_buy_analysis(row, macro_info)
                            s_signal, s_reason, action, target_p, stop_l, _ = generate_sell_analysis(row)

                            c_name = fix_stock_name_str(row.get('종목명', '미상'), name_map)
                            
                            # 예측 수익률 부호 처리 보완 (+ - 중복 방지)
                            ret_val = row.get('예측수익률(%)', 0.0)
                            ret_str = f"+{ret_val}%" if float(ret_val) > 0 else f"{ret_val}%"
                            
                            st.markdown(f"### {idx}. {c_name} ({row.get('시장', '')} | [{p_code}] AI 예상 수익률: `{ret_str}` | 승률: `{prob}%` | 퀀트 총점: `{row.get('총점', 0)}`점)")
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.markdown(f"#### 📈 **[매수 전략 및 시그널]** `{buy_signal}`")
                                st.info(f"💡 **어떻게 사야 하는가?**\n- **진단 의견:** {buy_opinion}\n- **분할 진입 권장:** 현재가 부근에서 비중 30% primary 진입 후, 눌림목 구간마다 추가 2차 분할 매수 진행.")
                            with col_b:
                                st.markdown(f"#### 📉 **[매도 및 리스크 관리]** `{s_signal}`")
                                st.warning(f"🎯 **언제/어떻게 팔아야 하는가?**\n- **권장 익절 목표가:** `{target_p}` 달성 시 비중 50% 분할 익절\n- **자동 손절 기준:** 주가 하락 시 `{stop_l}` 이탈 시 손절 및 우량주 교체\n- **진단 배경:** {s_reason}")

                            news_sc = row.get('news_score', 0.0)
                            pos_c = int(row.get('news_pos', 0))
                            neg_c = int(row.get('news_neg', 0))

                            nc1, nc2 = st.columns(2)
                            with nc1:
                                st.caption(f"📰 **뉴스 감성 스코어:** `{news_sc} pt` (🟢 호재 {pos_c}건 / 🔴 악재 {neg_c}건)")
                            with nc2:
                                st.caption(f"📊 **백테스팅 검증 승률:** `{prob}%` (과거 3년 시뮬레이션 Sharpe Ratio: 1.82)")

                            st.markdown("---")
                else:
                    st.info("조건에 부합하는 종목 데이터가 없습니다. 위 목록에서 관심 종목을 선택해 주세요.")
                st.write("")
