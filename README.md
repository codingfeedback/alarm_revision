# 증권사 리비전 알림 프로젝트

장고 + SQLite + 텔레그램 기반으로 국내/해외 목표주가 리비전을 수집하고 알림을 보내는 프로젝트입니다.

## 현재 운영 방식

- 국내 정기 알림: 평일 07:30, 주말 09:00
- 국내 수시 알림: 매일 08:00부터 1시간 간격
- 해외 정기 알림: 미국 DST일 때 10:15, 표준시일 때 11:15
- 정기 알림: 신호가 없어도 발송
- 수시 알림: 새 리비전 신호가 생길 때만 발송
- 기준: 최근 7일, 서로 다른 증권사 2곳 이상 목표가 상향/하향 리비전

## 핵심 구성

- `research/services/naver.py`: 네이버 리서치 수집
- `research/services/fmp.py`: 해외 가격목표 API 수집
- `research/services/ingestion.py`: 리포트 DB 적재
- `alerts/services/revision_detector.py`: 리비전 판정 및 메시지 요약
- `alerts/services/digests.py`: 정기 요약 메시지 생성
- `alerts/services/orchestrator.py`: 수시 알림 전송

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 아래 값을 채웁니다.

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ENABLE_TELEGRAM_ALERTS=True

DEFAULT_ALERT_RULE_NAME=default-2x-revision
DEFAULT_MIN_REVISION_COUNT=2
DEFAULT_LOOKBACK_DAYS=7
DEFAULT_MIN_REVISION_RATIO=0
DEFAULT_IMMEDIATE_REVISION_RATIO=9999
DEFAULT_WATCHLIST_ONLY=False

OVERSEAS_FMP_API_KEY=
OVERSEAS_TICKERS=AAPL,MSFT,NVDA,AMZN,TSLA
OVERSEAS_PRICE_TARGET_LIMIT=30
```

## 해외 API 설정

현재 해외 데이터는 Financial Modeling Prep(FMP) 기준으로 붙어 있습니다.

1. [FMP 개발자 페이지](https://site.financialmodelingprep.com/developer)에서 가입
2. 로그인 후 [Dashboard](https://site.financialmodelingprep.com/developer/docs/dashboard)에서 API Key 확인
3. `.env`에 `OVERSEAS_FMP_API_KEY=발급받은키` 입력
4. 필요한 미국 티커를 `OVERSEAS_TICKERS`에 쉼표로 입력

관련 공식 문서:
- [Quickstart](https://site.financialmodelingprep.com/developer/docs/quickstart)
- [Price Target API 문서](https://site.financialmodelingprep.com/developer/docs/price-target-api)
- [Price Target Consensus API 문서](https://site.financialmodelingprep.com/developer/docs/stable/price-target-consensus)
- [Pricing](https://site.financialmodelingprep.com/developer/docs/pricing)

주의:
- 현재 구현은 FMP API 키가 없으면 해외 정기 알림에서 안내 문구만 보냅니다.
- 무료 플랜의 엔드포인트 접근 범위는 변경될 수 있으니, 실제 사용 전 Dashboard에서 호출 가능 여부를 확인해야 합니다.

## 주요 명령

국내 정기 알림 1회 실행:

```powershell
python manage.py send_scheduled_digest --region domestic --pages 3
```

해외 정기 알림 1회 실행:

```powershell
python manage.py send_scheduled_digest --region overseas --respect-us-dst dst
python manage.py send_scheduled_digest --region overseas --respect-us-dst standard
```

수시 모니터링 1회 실행:

```powershell
python manage.py run_live_monitor --naver-pages 1
```

테스트:

```powershell
python manage.py check
python manage.py test
```

## 작업 스케줄러 스크립트

- `scripts/register_daily_0845_task.ps1`: 국내 정기 알림 등록(평일 07:30 / 주말 09:00)
- `scripts/register_live_monitor_task.ps1`: 국내 수시 모니터링 등록
- `scripts/register_overseas_digest_tasks.ps1`: 해외 DST/표준시 정기 알림 등록
- `scripts/enable_wake_for_tasks.ps1`: WakeToRun 및 wake timers 활성화

## 절전 관련

현재 작업은 모두 `WakeToRun=True`로 설정했고 Windows wake timers도 켰습니다.

하지만 아래 경우에는 자동 실행이 보장되지 않습니다.
- 최대 절전(Hibernate)
- 전원 꺼짐(Shutdown)
- BIOS/메인보드에서 wake timer 차단
- 노트북/PC 전원 정책이 wake 이벤트를 막는 경우

가장 안정적인 운영은:
- 데스크탑 전원 연결 유지
- 최대 절전 끄기
- 일반 Sleep만 사용
