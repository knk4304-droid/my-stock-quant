import datetime
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import streamlit as st

# 실시간 자동 새로고침 패키지
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

# ==========================================
# 1. 실시간 주요 지수 수집
# ==========================================
def fetch_realtime_macro():
    macro_results = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        url_kr = "https://m.stock.naver.com/api/index/KOSPI/basic"
        res = requests.get(url_kr, headers=headers, timeout=3).json()
        curr = float(res['closePrice'].replace(',', ''))
        rate = float(res['fluctuationsRatio'])
        macro_results['KOSPI'] = {'val': curr, 'change': rate}
    except Exception:
        macro_results['KOSPI'] = {'val': 0.0, 'change': 0.0}

    try:
        url_kq = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
        res = requests.get(url_kq, headers=headers, timeout=3).json()
        curr = float(res['closePrice'].replace(',', ''))
        rate = float(res['fluctuationsRatio'])
        macro_results['KOSDAQ'] = {'val': curr, 'change': rate}
    except Exception:
        macro_results['KOSDAQ'] = {'val': 0.0, 'change': 0.0}

    try:
        url_fx = "https://m.stock.naver.com/api/marketIndex/FX_USDKRW/basic"
        res = requests.get(url_fx, headers=headers, timeout=3).json()
        curr = float(res['closePrice'].replace(',', ''))
        rate = float(res['fluctuationsRatio'])
        macro_results['USDKRW'] = {'val': curr, 'change': rate}
    except Exception:
        try:
            fx_sub = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=3).json()
            curr = float(fx_sub['rates']['KRW'])
            macro_results['USDKRW'] = {'val': curr, 'change': 0.0}
        except Exception:
            macro_results['USDKRW'] = {'val': 1350.00, 'change': 0.0}

    us_tickers = {'S&P500': '^GSPC', 'NASDAQ': '^IXIC', 'VIX': '^VIX'}
    for key, sym in us_tickers.items():
        try:
            hist = yf.Ticker(sym).history(period='5d', timeout=3)
            if not hist.empty and len(hist) >= 2:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                rate = (curr - prev) / prev * 100
                macro_results[key] = {'val': curr, 'change': rate}
            else:
                macro_results[key] = {'val': 0.0, 'change': 0.0}
        except Exception:
            macro_results[key] = {'val': 0.0, 'change': 0.0}

    return macro_results


# ==========================================
# 2. 유니버스 로드
# ==========================================
class UniverseLoader:
    @staticmethod
    def get_full_universe():
        name_map = {
            '005930.KS': '삼성전자', '000660.KS': 'SK하이닉스', '035420.KS': 'NAVER', '005380.KS': '현대차',
            '000270.KS': '기아', '068270.KS': '셀트리온', '005490.KS': 'POSCO홀딩스', '035720.KS': '카카오',
            '051910.KS': 'LG화학', '006400.KS': '삼성SDI', '373220.KS': 'LG에너지솔루션', '207940.KS': '삼성바이오로직스',
            '105560.KS': 'KB금융', '055550.KS': '신한지주', '086790.KS': '하나금융지주', '015760.KS': '한국전력',
            '003550.KS': 'LG', '018260.KS': '삼성SDS', '010140.KS': '삼성중공업', '009150.KS': '삼성전기',
            '032830.KS': '삼성생명', '000810.KS': '삼성화재', '017670.KS': 'SK텔레콤', '096770.KS': 'SK이노베이션',
            '011200.KS': 'HMM', '012330.KS': '현대모비스', '034020.KS': '두산에너빌리티', '010950.KS': 'S-Oil',
            '003670.KS': '포스코퓨처엠', '329180.KS': 'HD현대중공업', '267250.KS': 'HD
