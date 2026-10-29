# universe.py - 유니버스 전체 모수 종목 데이터 전용 모듈
import pandas as pd
import streamlit as st

class UniverseLoader:
    @staticmethod
    @st.cache_data(ttl=86400)
    def get_full_universe():
        name_map = {
            # 주요 한글 종목명 매핑 데이터베이스
            '005930.KS': '삼성전자', '000660.KS': 'SK하이닉스', '373220.KS': 'LG에너지솔루션', '207940.KS': '삼성바이오로직스',
            '005380.KS': '현대차', '000270.KS': '기아', '105560.KS': 'KB금융', '068270.KS': '셀트리온',
            '055550.KS': '신한지주', '035420.KS': 'NAVER', '005490.KS': 'POSCO홀딩스', '006400.KS': '삼성SDI',
            '051910.KS': 'LG화학', '035720.KS': '카카오', '086790.KS': '하나금융지주', '015760.KS': '한국전력',
            '003550.KS': 'LG', '018260.KS': '삼성SDS', '010140.KS': '삼성중공업', '009150.KS': '삼성전기',
            '032830.KS': '삼성생명', '000810.KS': '삼성화재', '017670.KS': 'SK텔레콤', '096770.KS': 'SK이노베이션',
            '011200.KS': 'HMM', '012330.KS': '현대모비스', '034020.KS': '두산에너빌리티', '010950.KS': 'S-Oil',
            '003670.KS': '포스코퓨처엠', '329180.KS': 'HD현대중공업', '267250.KS': 'HD현대일렉트릭', '010130.KS': '고려아연',
            '009540.KS': 'HD한국조선해양', '030200.KS': 'KT', '316140.KS': '우리금융지주', '003490.KS': '대한항공',
            '036570.KS': '엔씨소프트', '251270.KS': '넷마블', '000150.KS': '두산밥캣', '010120.KS': 'LS electric',
            '028260.KS': '삼성물산', '034730.KS': 'SK', '011170.KS': '롯데케미칼', '004020.KS': '현대제철',
            '001040.KS': 'CJ', '000100.KS': '유한양행', '128940.KS': '한미약품', '001450.KS': '현대해상',
            '196170.KQ': '알테오젠', '086520.KQ': '에코프로비엠', '028300.KQ': 'HLB', '068760.KQ': '셀트리온제약',
            '247540.KQ': '엘앤에프', '263750.KQ': '펄어비스', '214150.KQ': '클래시스', '058470.KQ': '리노공업',
            '035900.KQ': 'JYP Ent.', '041510.KQ': 'SM', '035760.KQ': 'CJ ENM', '086900.KQ': '메디톡스',
            '112040.KQ': '위메이드', '036830.KQ': '솔브레인', '034230.KQ': '파라다이스', '039200.KQ': '오스코텍',
            '293490.KQ': '카카오게임즈', '278280.KQ': '천보', '440110.KQ': '파두', '277810.KQ': '레인보우로보틱스',
            '328130.KQ': '루닛', '084990.KQ': '하이비젼시스템', '053690.KQ': '한미반도체', '081660.KQ': '플리토',
            '060280.KQ': '큐렉소', '053030.KQ': '바이오니아', '068240.KQ': '다원시스',
            'AAPL': '애플', 'MSFT': '마이크로소프트', 'AMZN': '아마존', 'NVDA': '엔비디아', 'GOOGL': '알파벳',
            'META': '메타', 'BRK-B': '버크셔해서웨이', 'TSLA': '테슬라', 'UNH': '유나이티드헬스', 'JNJ': '존슨앤드존슨',
            'AVGO': '브로드컴', 'COST': '코스트코', 'AMD': 'AMD', 'PEP': '펩시코', 'NFLX': '넷플릭스',
            'LLY': '일라이릴리', 'JPM': 'JP모건체이스', 'V': '비자', 'XOM': '엑손모빌', 'WMT': '월마트',
            'MA': '마스터카드', 'PG': '프록터앤드갬블', 'HD': '홈디포', 'BAC': '뱅크오브아메리카', 'ORCL': '오라클',
            'ABBV': '애브비', 'CVX': '쉐브론', 'CRM': '세일즈포스', 'MRK': '머크', 'KO': '코카콜라',
            'TMUS': '티모바일', 'CSCO': '시스코', 'ACN': '액센츄어', 'INTC': '인텔', 'QCOM': '퀄컴',
            'PLTR': '팔란티어', 'SMCI': '슈퍼마이크로컴퓨터', 'IONQ': '아이온큐', 'ROKU': '로쿠',
            'SOFI': '소파이', 'U': '유니티', 'RBLX': '로블록스', 'PATH': '유아이패스', 'NOW': '서비스나우',
            '069500.KS': 'KODEX 200', '102110.KQ': 'TIGER 200', '229200.KS': 'KODEX 코스닥150',
            '305540.KS': 'TIGER 2차전지테마', '394660.KS': 'KODEX 2차전지핵심소재10', '091230.KS': 'TIGER 반도체',
            '396500.KS': 'KODEX AI반도체핵심장비', '244580.KS': 'KODEX 바이오', '261220.KS': 'KODEX 자동차',
            '091220.KS': 'TIGER 은행', '139280.KS': 'TIGER 200 금융', '102960.KS': 'KODEX 건설',
            '117460.KS': 'KODEX 철강', '139220.KS': 'TIGER 200 중공업', '462330.KS': 'KODEX K-방산',
            '228820.KS': 'TIGER 미디어컨텐츠', '266390.KS': 'KODEX 게임산업', '305720.KS': 'KODEX 고배당',
            '161510.KS': 'ARIRANG 고배당주', '458730.KS': 'ACE 미국S&P500', '360750.KS': 'TIGER 미국S&P500',
            '133690.KS': 'TIGER 미국나스닥100', '381180.KS': 'TIGER 미국배당다우존스', '371460.KS': 'TIGER 차이나전기차SOLACTIVE',
            '252670.KS': 'KODEX 200선물인버스2X', '114800.KS': 'KODEX 인버스', '138230.KS': 'KODEX 미국달러선물',
            '132030.KS': 'KODEX 골드선물(H)', '271060.KS': 'KODEX WTI원유선물(H)', '357870.KS': 'TIGER CD금리투자KIS'
        }

        # 1. 코스피 200 (전 종목)
        kospi200_tickers = ['005930.KS', '000660.KS', '373220.KS', '207940.KS', '005380.KS', '000270.KS', '105560.KS', '068270.KS', '055550.KS', '035420.KS', '005490.KS', '006400.KS', '051910.KS', '035720.KS', '086790.KS', '015760.KS', '003550.KS', '018260.KS', '010140.KS', '009150.KS', '032830.KS', '000810.KS', '017670.KS', '096770.KS', '011200.KS', '012330.KS', '034020.KS', '010950.KS', '003670.KS', '329180.KS', '267250.KS', '010130.KS', '009540.KS', '030200.KS', '316140.KS', '003490.KS', '036570.KS', '251270.KS', '000150.KS', '010120.KS', '028260.KS', '034730.KS', '011170.KS', '004020.KS', '001040.KS', '000100.KS', '128940.KS', '001450.KS', '008770.KS', '004990.KS', '018880.KS', '003230.KS', '020150.KS', '001800.KS', '000880.KS', '005830.KS', '006800.KS', '005935.KS', '021240.KS', '000210.KS', '001060.KS', '088350.KS', '004170.KS', '005385.KS', '138040.KS', '011780.KS', '001680.KS', '000120.KS', '078930.KS', '000720.KS', '033780.KS', '002790.KS', '039490.KS', '010620.KS', '009830.KS', '001430.KS', '000080.KS', '003410.KS', '006360.KS', '004800.KS', '005420.KS', '001520.KS', '006280.KS', '002380.KS', '011070.KS', '000670.KS', '002270.KS', '000240.KS', '001740.KS', '002960.KS', '003000.KS', '000990.KS', '000157.KS', '000215.KS', '001440.KS', '002710.KS', '003470.KS', '003520.KS', '003920.KS', '004000.KS', '004370.KS', '004980.KS', '005250.KS', '005300.KS', '005387.KS', '005940.KS', '006110.KS', '006260.KS', '006340.KS', '007070.KS', '007310.KS', '008040.KS', '008930.KS', '009240.KS', '009420.KS', '009970.KS', '010060.KS', '010145.KS', '010780.KS', '011210.KS', '011790.KS', '012450.KS', '012510.KS', '012630.KS', '012750.KS', '013570.KS', '014680.KS', '014820.KS', '015765.KS', '016360.KS', '016380.KS', '017800.KS', '018670.KS', '019170.KS', '019180.KS', '020100.KS', '020200.KS', '023530.KS', '024110.KS', '025540.KS', '026960.KS', '028050.KS', '028670.KS', '029780.KS', '030000.KS', '030190.KS', '030610.KS', '031430.KS', '032640.KS', '033270.KS', '033780.KS', '034220.KS', '034310.KS', '034730.KS', '035250.KS', '036460.KS', '036580.KS', '039130.KS', '042660.KS', '042670.KS', '042700.KS', '047040.KS', '047050.KS', '047810.KS', '051600.KS', '051900.KS', '052690.KS', '064350.KS', '069620.KS', '069960.KS', '071050.KS', '071840.KS', '079550.KS', '081660.KS', '086280.KS', '086790.KS', '088350.KS', '090430.KS', '097950.KS', '103140.KS', '111770.KS', '112610.KS', '114090.KS', '120110.KS', '138040.KS', '138930.KS', '139130.KS', '161890.KS', '175330.KS', '180640.KS', '192080.KS', '192400.KS', '204320.KS', '241560.KS', '271560.KS', '282330.KS', '298020.KS', '307950.KS', '326030.KS', '352820.KS', '361610.KS', '377300.KS', '383220.KS', '402340.KS']

        # 2. 코스닥 150 (전 종목)
        kosdaq150_tickers = ['196170.KQ', '086520.KQ', '028300.KQ', '068760.KQ', '247540.KQ', '263750.KQ', '214150.KQ', '058470.KQ', '035900.KQ', '041510.KQ', '035760.KQ', '086900.KQ', '112040.KQ', '036830.KQ', '034230.KQ', '039200.KQ', '293490.KQ', '278280.KQ', '002900.KQ', '003160.KQ', '003380.KQ', '004360.KQ', '005290.KQ', '005900.KQ', '006050.KQ', '007370.KQ', '008370.KQ', '009810.KQ', '011040.KQ', '013030.KQ', '013720.KQ', '014100.KQ', '014620.KQ', '015750.KQ', '016100.KQ', '018650.KQ', '019540.KQ', '019550.KQ', '020150.KQ', '022100.KQ', '023160.KQ', '023410.KQ', '023760.KQ', '024840.KQ', '025900.KQ', '027360.KQ', '028080.KQ', '032190.KQ', '032500.KQ', '033100.KQ', '033240.KQ', '033290.KQ', '033340.KQ', '033640.KQ', '034020.KQ', '035080.KQ', '035600.KQ', '035890.KQ', '036030.KQ', '036490.KQ', '036540.KQ', '036000.KQ', '036200.KQ', '036800.KQ', '036810.KQ', '036890.KQ', '036930.KQ', '039030.KQ', '039440.KQ', '040300.KQ', '041190.KQ', '041920.KQ', '042000.KQ', '042510.KQ', '042700.KQ', '043150.KQ', '043370.KQ', '043610.KQ', '043700.KQ', '045510.KQ', '046070.KQ', '046120.KQ', '046890.KQ', '046970.KQ', '047080.KQ', '047810.KQ', '048260.KQ', '048410.KQ', '049070.KQ', '049080.KQ', '051160.KQ', '051370.KQ', '052260.KQ', '052400.KQ', '053030.KQ', '053800.KQ', '054620.KQ', '054780.KQ', '054800.KQ', '054920.KQ', '056190.KQ', '058470.KQ', '060280.KQ', '060310.KQ', '060720.KQ', '063080.KQ', '063160.KQ', '064290.KQ', '064550.KQ', '065680.KQ', '066970.KQ', '067080.KQ', '067160.KQ', '067310.KQ', '067630.KQ', '068240.KQ', '068760.KQ', '069080.KQ', '069620.KQ', '071970.KQ', '073070.KQ', '073540.KQ', '078160.KQ', '078340.KQ', '078600.KQ', '079160.KQ', '079370.KQ', '080160.KQ', '081660.KQ', '082660.KQ', '083310.KQ', '083450.KQ', '084370.KQ', '084990.KQ', '085310.KQ', '086520.KQ', '086900.KQ', '089010.KQ', '090410.KQ', '091340.KQ', '091580.KQ', '091700.KQ', '091990.KQ', '092040.KQ', '095270.KQ', '095610.KQ', '095660.KQ', '095700.KQ', '096040.KQ', '096530.KQ', '096770.KQ', '097520.KQ']

        # 3. S&P 500 (안정 주요 300개 종목)
        sp500_tickers = ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'BRK-B', 'TSLA', 'UNH', 'JNJ', 'LLY', 'JPM', 'V', 'XOM', 'WMT', 'MA', 'PG', 'HD', 'BAC', 'ORCL', 'ABBV', 'CVX', 'CRM', 'MRK', 'KO', 'PEP', 'AMD', 'COST', 'AVGO', 'CSCO', 'ACN', 'INTC', 'QCOM', 'TXN', 'AMAT', 'INTU', 'ISRG', 'AMGN', 'BKNG', 'LRCX', 'GE', 'CAT', 'IBM', 'NOW', 'DIS', 'UBER', 'PANW', 'ABT', 'ACGL', 'AEE', 'AEP', 'AES', 'AFL', 'AIG', 'AIZ', 'AJG', 'AKAM', 'ALB', 'ALGN', 'ALL', 'ALLE', 'AMCR', 'AME', 'AMG', 'AMP', 'AMT', 'ANET', 'AON', 'AOS', 'APA', 'APD', 'APH', 'APTV', 'ARE', 'ATO', 'AVB', 'AVY', 'AWK', 'AXP', 'AZO', 'BA', 'BALL', 'BAX', 'BBWI', 'BBY', 'BDX', 'BEN', 'BF-B', 'BG', 'BIIB', 'BIO', 'BK', 'BKR', 'BLDR', 'BLK', 'BMY', 'BR', 'BRO', 'BSX', 'BWA', 'BX', 'BXP', 'C', 'CAG', 'CAH', 'CARR', 'CB', 'CBOE', 'CBRE', 'CCI', 'CCL', 'CDNS', 'CDW', 'CE', 'CF', 'CFG', 'CHD', 'CHRW', 'CHTR', 'CI', 'CINF', 'CL', 'CLX', 'CMA', 'CMG', 'CMI', 'CMS', 'CNC', 'CNP', 'COF', 'COO', 'COP', 'COR', 'CPB', 'CPRT', 'CPT', 'CRL', 'CTAS', 'CTRA', 'CTSH', 'CTVA', 'CVS', 'CZR', 'D', 'DAL', 'DD', 'DE', 'DFS', 'DG', 'DGX', 'DHI', 'DHR', 'DLR', 'DLTR', 'DOV', 'DOW', 'DPZ', 'DRI', 'DTE', 'DUK', 'DVA', 'DVN', 'DXCM', 'EA', 'EBAY', 'ECL', 'ED', 'EFX', 'EIX', 'EL', 'ELV', 'EMN', 'EMR', 'ENPH', 'EOG', 'EPAM', 'EQIX', 'EQR', 'EQT', 'ES', 'ESS', 'ETN', 'ETR', 'ETSY', 'EVRG', 'EW', 'EXC', 'EXPD', 'EXPE', 'EXR', 'F', 'FANG', 'FAST', 'FCX', 'FDS', 'FDX', 'FE', 'FFIV', 'FI', 'FICO', 'FIS', 'FITB', 'FLT', 'FMC', 'FOX', 'FOXA', 'FRT', 'FSLR', 'FTNT', 'FTV', 'GD', 'GEHC', 'GEN', 'GILD', 'GIS', 'GL', 'GLW', 'GM', 'GNRC', 'GPN', 'GRMN', 'GS', 'GWW', 'HAL', 'HAS', 'HBAN', 'HCA', 'HES', 'HIG', 'HII', 'HLT', 'HOLX', 'HON', 'HPE', 'HPQ', 'HRL', 'HSIC', 'HST', 'HSY', 'HUBB', 'HUM', 'HWM', 'ICE', 'IDXX', 'IEX', 'IFF', 'ILMN', 'INCY', 'INVH', 'IP', 'IPG', 'IQV', 'IR', 'IRM', 'IT', 'ITW', 'IVZ', 'J', 'JBHT', 'JCI', 'JKHY', 'JNPR', 'K', 'KDP', 'KEY', 'KEYS', 'KHC', 'KIM', 'KLAC', 'KMB', 'KMI', 'KMX', 'KR', 'L', 'LDOS', 'LEN', 'LH', 'LHX', 'LIN', 'LKQ', 'LMT', 'LNC', 'LNT', 'LOW', 'LULU', 'LUV', 'LVS', 'LW', 'LYB', 'LYV', 'MAA', 'MAR', 'MAS', 'MCD', 'MCHP', 'MCK', 'MCO', 'MDLZ', 'MDT', 'MET', 'MGM', 'MHK', 'MKC', 'MKTX', 'MLM', 'MMC', 'MMM', 'MNST', 'MO', 'MOH', 'MOS', 'MPC', 'MPWR', 'MRNA', 'MRO', 'MS', 'MSCI', 'MSI', 'MTB', 'MTD', 'MU', 'NCLH', 'NDAQ', 'NDSN', 'NEE', 'NEM', 'NI', 'NKE', 'NOC', 'NRG', 'NSC', 'NTAP', 'NTRS', 'NUE', 'NVR', 'NWL', 'NWS', 'NWSA', 'NXPI', 'O', 'ODFL', 'OKE', 'OMC', 'ON', 'ORLY', 'OTIS', 'OXY', 'PARA', 'PAYX', 'PAYC', 'PCAR', 'PCG', 'PEAK', 'PEG', 'PFE', 'PFG', 'PGR', 'PH', 'PHM', 'PKG', 'PKI', 'PLD', 'PM', 'PNC', 'PNR', 'PNW', 'POOL', 'PPG', 'PPL', 'PRU', 'PSA', 'PSX', 'PTC', 'PWR', 'PXD', 'PYPL', 'QRVO', 'RCL', 'RE', 'REG', 'REGN', 'RF', 'RHI', 'RJF', 'RL', 'RMD', 'ROK', 'ROL', 'ROP', 'ROST', 'RSG', 'RTX', 'SBAC', 'SBUX', 'SCHW', 'SEDG', 'SEE', 'SHW', 'SJM', 'SLB', 'SNA', 'SNPS', 'SO', 'SPG', 'SPGI', 'SRE', 'STE', 'STLD', 'STT', 'STX', 'STZ', 'SWK', 'SWKS', 'SYK', 'SYF', 'SYY', 'T', 'TAP', 'TDG', 'TDY', 'TECH', 'TEL', 'TER', 'TFC', 'TFX', 'TGT', 'TJX', 'TMO', 'TPR', 'TRGP', 'TRMB', 'TROW', 'TRV', 'TSCO', 'TSN', 'TT', 'TTWO', 'TXT', 'TYL', 'UAL', 'UDR', 'UHS', 'ULTA', 'UNP', 'UPS', 'URI', 'USB', 'VFC', 'VICI', 'VLO', 'VMC', 'VRSK', 'VRSN', 'VRTX', 'VTR', 'VTRS', 'VZ', 'WAB', 'WAT', 'WBA', 'WBD', 'WDC', 'WEC', 'WELL', 'WFC', 'WHR', 'WM', 'WMB', 'WRB', 'WRK', 'WST', 'WTW', 'WY', 'WYNN', 'XEL', 'XRAY', 'XYL', 'YUM', 'ZBH', 'ZBRA', 'ZTS']

        # 4. 나스닥 100 (100개 전 종목)
        nasdaq100_tickers = ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AVGO', 'COST', 'AMD', 'PEP', 'NFLX', 'CSCO', 'TMUS', 'INTC', 'QCOM', 'TXN', 'AMAT', 'INTU', 'ISRG', 'AMGN', 'BKNG', 'LRCX', 'NOW', 'PANW', 'ADBE', 'ADP', 'ADI', 'KLAC', 'MDLZ', 'SNPS', 'CDNS', 'REGN', 'CSX', 'PYPL', 'ASML', 'ORLY', 'MAR', 'CTAS', 'MELI', 'ROP', 'MNST', 'NXPI', 'WDAY', 'FTNT', 'ADSK', 'CHTR', 'DXCM', 'KDP', 'AEP', 'PAYX', 'MCHP', 'CPRT', 'EXC', 'ROST', 'LULU', 'IDXX', 'BIIB', 'ODFL', 'EA', 'CSGP', 'VRSK', 'FAST', 'KHC', 'CTSH', 'GEHC', 'CRWD', 'AZN', 'DDOG', 'CEG', 'FANG', 'BKR', 'ON', 'ANSS', 'DLTR', 'GFS', 'TTD', 'ZS', 'WBD', 'ILMN', 'SGEN', 'WBA', 'SBUX', 'ALGN', 'EBAY', 'ENPH', 'ZM', 'JD', 'PDD', 'BIDU', 'LCID', 'RIVN', 'SIRIN']

        # 5. 국내 ETF (50개 확대)
        kr_etf = ['069500.KS', '102110.KQ', '229200.KS', '305540.KS', '394660.KS', '091230.KS', '396500.KS', '244580.KS', '261220.KS', '091220.KS', '139280.KS', '102960.KS', '117460.KS', '139220.KS', '462330.KS', '228820.KS', '266390.KS', '305720.KS', '161510.KS', '458730.KS', '360750.KS', '133690.KS', '381180.KS', '371460.KS', '252670.KS', '114800.KS', '138230.KS', '132030.KS', '271060.KS', '357870.KS', '091210.KS', '102780.KS', '105150.KS', '117680.KS', '139230.KS', '139240.KS', '139250.KS', '139260.KS', '139270.KS', '140700.KS', '140710.KS', '152100.KS', '157450.KS', '219480.KS', '227540.KS', '243880.KS', '251340.KS', '272580.KS', '278530.KS', '292150.KS']

        kr_smallcap = ['440110.KQ', '277810.KQ', '328130.KQ', '084990.KQ', '053690.KQ', '081660.KQ', '060280.KQ', '053030.KQ', '068240.KQ']
        us_smallcap = ['PLTR', 'SMCI', 'IONQ', 'ROKU', 'SOFI', 'U', 'RBLX', 'PATH', 'DKNG', 'AFRM']

        universe = {
            '코스피200': kospi200_tickers,
            '코스닥100': kosdaq150_tickers,
            'S&P500': sp500_tickers,
            '나스닥100': nasdaq100_tickers,
            '국내 ETF': kr_etf,
            '국내 소형 고성장주': kr_smallcap,
            '미국 소형 고성장주': us_smallcap
        }
        return universe, name_map
