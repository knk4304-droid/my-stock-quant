# AI STOCK MASTER 통합 검증 및 공유 안내

## 한 번에 업데이트
1. 이 ZIP의 파일을 기존 GitHub 저장소의 같은 경로에 교체/추가합니다. 기존 다른 파일은 지우지 않습니다.
2. GitHub Actions > Market scan v9 > Run workflow를 실행합니다.
3. GitHub Actions 로그의 `Validate stored recommendation data` 성공을 확인합니다.
4. Streamlit Cloud 앱을 열어 메뉴, 추천 후보, 관심종목 분석, 추천 성과 검증을 확인합니다.

## 검증 범위
- `release_verification.py`는 Python 구문, 주요 메뉴, 통계 계산, 미성숙 관측값 제외, 날짜/수익률 오류 탐지를 점검합니다.
- 실제 추천 기록의 통계적 우위는 관측 데이터가 쌓여야 평가할 수 있습니다.
- 1·5·20거래일 경과 전 `None`은 정상적인 관측 대기입니다.
- 이 릴리스는 실거래 주문 기능을 추가하지 않습니다.

## 다른 사람에게 보기 전용으로 공유
- Streamlit 앱의 웹 주소를 그대로 전달하면 됩니다. 공개 앱이라면 별도 계정 없이 열람 가능합니다.
- Streamlit Community Cloud의 앱 설정에서 공개 여부와 접근 권한을 확인합니다.
- GitHub 저장소 편집 권한을 주지 마세요. 코드와 데이터가 포함된 저장소를 공개할 경우 민감한 파일을 먼저 점검하세요.
- Streamlit secrets, API 키, Supabase 키, 증권계좌 연결 정보, 개인 거래 기록은 공개 화면과 저장소에 넣지 마세요.
- 앱을 공동 편집하려면 별도 접근 권한 관리가 필요하며, 보기 전용 링크 공유와 다릅니다.
- 공개 전 앱에 관리자 기능/민감 데이터가 표시되는지 확인하세요. 기존 관리 메뉴를 숨기는 것만으로 접근 통제가 되는 것은 아닙니다.

## 유용한 링크
- GitHub: https://github.com/knk4304-droid/my-stock-quant
- Actions: https://github.com/knk4304-droid/my-stock-quant/actions
- Streamlit Community Cloud: https://share.streamlit.io/
