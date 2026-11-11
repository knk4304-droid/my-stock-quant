# AI STOCK MASTER 최종 통합 후보 — 설치 및 검증 안내

## 이번 통합 변경
- `final_decision.py`: 비정상 가격, NaN, 손익비 미달, 점수 누락을 제외하는 순수 함수 기반 선정 로직
- `simple_dashboard.py`: 기존 기능 유지, 선정 제외 사유 표시, 종합의견에 안전한 선정 로직 연결, 월요일 10시 기준시각 대비 저장 분석 최신성 표시
- `test_final_decision.py`: 오프라인 선정·정렬·주간 기준시각 테스트
- 추천 참고점수 설명은 `st.text`로 출력하여 Markdown의 물결표 취소선 해석을 피함. 브라우저에 과거 코드가 캐시되어 있으면 배포 후 새로고침 필요.

## 업로드 방법
1. 전체 ZIP은 보관·복구용입니다. 기존 GitHub 저장소에 업로드할 때는 `AI_STOCK_MASTER_changed_files_only.zip`의 파일만 저장소 루트에 덮어쓰세요.
2. GitHub https://github.com/knk4304-droid/my-stock-quant 에서 `Add file` → `Upload files`를 선택합니다.
3. `simple_dashboard.py`, `final_decision.py`, `test_final_decision.py`, `FINAL_RELEASE_GUIDE_KO.md`만 업로드하고 Commit합니다. ZIP 자체를 저장소에 올리지 마세요.
4. Streamlit 앱이 최신 커밋을 반영했는지 확인하고 브라우저에서 강력 새로고침(Ctrl+F5)을 수행하세요.
5. GitHub Actions https://github.com/knk4304-droid/my-stock-quant/actions 에서 `Market scan v9` 수동 실행 및 로그를 확인하세요.

## 완료된 오프라인 검증
- `python -m compileall -q .`: 통과
- `python -m pytest -q test_final_decision.py test_admin_access.py test_ranking_options.py`: 13개 통과
- `python release_verification.py`: 통과
- `python validation_smoke.py --data market_scan_data/recommendation_history.csv`: 통과

## 미완료 및 제한
- 전체 pytest 테스트: 로컬 환경에 yfinance가 없어 전체 수집 단계에서 중단. 전체 테스트 통과로 주장할 수 없음.
- 외부 가격·뉴스·공시 API 실시간 연결, Streamlit 브라우저 UI 렌더링, GitHub Actions 배포 후 재실행은 별도 환경에서 확인 필요.
- 최근 추천 기록: 1거래일 관측 65/90, 5·20거래일 관측 0/90. 표본 부족으로 수익성 검증 불가.
- 월요일 10시 스케줄은 기존 `.github/workflows/market_scan_v90.yml`에 이미 설정됨. 예약 실행은 정확히 10시 완료를 보장하지 않음.
- 뉴스 제목으로 호재·악재를 확정하지 않음. 실적·공시 원문 확인 전에는 매수 주문을 보류하는 설계.
- 실제 계좌 연결 및 실거래 주문 없음.

## 권장 최종 운영 점검
- 국내 ETF / 미국 ETF / 한국 주식 / 미국 주식별 필터 확인
- 상위 10종목 상세 분석 → 종합의견 후보 0~3개 및 제외 사유 확인
- 월요일 10시 이후 `마지막 저장 분석` 표시가 갱신되는지 확인
- 뉴스 수집 오류 시 보류 안내 확인
- 관리자 비밀번호 또는 OIDC 설정 및 일반 사용자 관리자 접근 차단 확인
- Streamlit Secrets/API 키를 GitHub에 절대 커밋하지 말 것
