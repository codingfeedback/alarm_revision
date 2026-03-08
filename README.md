# 증권사 개정 알람 프로젝트

장고 + SQLite + 텔레그램 기반으로 목표주가 리비전 알림을 수집, 판단, 전송하는 데스크탑 우선 프로젝트다.

## 현재 구현 범위

- `research` 앱: 종목, 증권사, 애널리스트, 리포트, 관심종목 관리
- `alerts` 앱: 리비전 규칙, 이벤트 로그, 텔레그램 전송
- CSV 리포트 수입 커맨드
- 관심종목 CSV 수입 커맨드
- 네이버 리서치 목록 수집 커맨드
- 통합 데스크탑 파이프라인 커맨드
- 3회 중복 리비전 감지 로직
- Windows 실행 스크립트

## 기본 구조

- `research/services/naver.py`: 네이버 목록 수집 및 스냅샷 저장
- `research/services/csv_importer.py`: 리포트 CSV 대량 적재
- `research/services/watchlist_importer.py`: 관심종목 CSV 대량 적재
- `research/services/ingestion.py`: 리포트 DB upsert
- `alerts/services/revision_detector.py`: 리비전 판정
- `alerts/services/telegram.py`: 텔레그램 알림
- `alerts/services/orchestrator.py`: 전체 알림 사이클

## 빠른 시작

1. `.env.example`을 복사해 `.env`를 만든다.
2. 의존성을 설치한다.
3. 데이터베이스를 준비한다.

```powershell
python manage.py migrate
python manage.py bootstrap_demo_data
```

4. 전체 파이프라인을 실행한다.

```powershell
python manage.py run_desktop_pipeline --source naver --pages 1 --save-html
```

## 핵심 커맨드

리포트 CSV 적재:

```powershell
python manage.py import_reports_csv .\sample_reports.csv
```

관심종목 CSV 적재:

```powershell
python manage.py import_watchlist_csv .\watchlist.csv --disable-missing
```

룰 생성 또는 갱신:

```powershell
python manage.py upsert_alert_rule default-3x-revision --direction up --min-count 3 --lookback-days 5 --watchlist-only
```

텔레그램 테스트:

```powershell
python manage.py send_telegram_test --message "알림 테스트"
```

## CSV 예시 컬럼

리포트 CSV:

```text
source,source_report_id,symbol,security_name,market,brokerage_name,brokerage_code,analyst_name,title,report_date,published_at,target_price,previous_target_price,eps_forecast,opinion,report_url,summary
```

관심종목 CSV:

```text
symbol,security_name,market,priority,enabled,notes
005930,Samsung Electronics,KOSPI,1,true,core holding
000660,SK hynix,KOSPI,2,true,ai memory
```

## 운영 자동화 권장안

- 데스크탑: 실제 수집, 알림 실행, 스케줄러 등록 담당
- 노트북: 파서 수정, 규칙 튜닝, 결과 검토, git 병합 담당
- git 브랜치 전략:
  - `main`: 안정 버전
  - `codex/parser-*`: 수집기 실험
  - `codex/rule-*`: 판정 로직 실험
  - `codex/ops-*`: 스케줄러와 운영 자동화 작업
- Windows 작업 스케줄러:
  - 08:20: `scripts/run_desktop_cycle.ps1`
  - 08:40: `scripts/run_desktop_cycle.ps1`
  - 09:00~15:30: 30분 간격 반복
- 실행 결과 요약 JSON은 `data/runs/` 아래에 저장된다.

## 다음 우선 작업

- 네이버 상세 페이지에서 목표가와 EPS를 더 정교하게 추출
- 증권사별 직전 리포트 자동 연결 강화
- 애널리스트, 섹터 가중치 모델 추가
- 결과 요약을 텔레그램 일간 리포트 형태로 확장
