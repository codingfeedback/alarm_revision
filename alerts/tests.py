from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from alerts.models import AlertRule
from alerts.services.digests import build_digest_message, matches_us_dst_mode
from alerts.services.opinion_engine import assess_signal
from alerts.services.orchestrator import ensure_observation_rule, run_alert_cycle
from alerts.services.signal_analysis import analyze_signal
from alerts.services.telegram import chunk_message
from alerts.services.revision_detector import (
    attach_current_prices,
    detect_signals,
    is_stock_split_adjustment,
)
from research.models import Brokerage, ResearchReport, Security, WatchlistEntry
from research.services.ingestion import ingest_reports
from research.services.naver_quotes import StockPriceSnapshot
from research.services.schemas import ParsedReport


class RevisionDetectorTests(TestCase):
    def test_detects_two_upward_revisions(self) -> None:
        security = Security.objects.create(symbol="035420", name="NAVER", market="KOSPI")
        today = timezone.localdate()
        for index in range(2):
            brokerage = Brokerage.objects.create(name=f"Broker {index}")
            ResearchReport.objects.create(
                source="naver",
                source_report_id=f"manual-{index}",
                security=security,
                brokerage=brokerage,
                title=f"Report {index}",
                report_date=today - timedelta(days=index),
                published_at=timezone.now(),
                target_price=120000 + (index * 1000),
                previous_target_price=100000,
            )

        rule = AlertRule.objects.create(
            name="2x-up",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=2,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        signals = detect_signals(rule, sources=["naver"])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].security.symbol, "035420")

    def test_detects_two_downward_revisions(self) -> None:
        security = Security.objects.create(symbol="AAPL", name="Apple", market="US")
        today = timezone.localdate()
        for index in range(2):
            brokerage = Brokerage.objects.create(name=f"US Broker {index}")
            ResearchReport.objects.create(
                source="fmp",
                source_report_id=f"fmp-{index}",
                security=security,
                brokerage=brokerage,
                title=f"US Report {index}",
                report_date=today - timedelta(days=index),
                published_at=timezone.now(),
                target_price=180 - (index * 5),
                previous_target_price=200,
            )

        rule = AlertRule.objects.create(
            name="2x-down",
            direction=AlertRule.DIRECTION_DOWN,
            min_revision_count=2,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        signals = detect_signals(rule, sources=["fmp"])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].direction, AlertRule.DIRECTION_DOWN)

    def test_ignores_zero_revision_ratio(self) -> None:
        security = Security.objects.create(symbol="271560", name="오리온", market="KOSPI")
        brokerage = Brokerage.objects.create(name="NoChange Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="no-change",
            security=security,
            brokerage=brokerage,
            title="No change",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=100000,
            previous_target_price=100000,
        )

        rule = AlertRule.objects.create(
            name="ignore-zero",
            direction=AlertRule.DIRECTION_BOTH,
            min_revision_count=1,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        self.assertEqual(detect_signals(rule, sources=["naver"]), [])

    def test_ignores_stock_split_adjusted_target_price_drop(self) -> None:
        security = Security.objects.create(symbol="123450", name="분할테스트", market="KOSPI")
        today = timezone.localdate()
        for index in range(2):
            brokerage = Brokerage.objects.create(name=f"Split Broker {index}")
            report = ResearchReport.objects.create(
                source="naver",
                source_report_id=f"split-{index}",
                security=security,
                brokerage=brokerage,
                title="액면분할 반영 목표가 조정",
                summary="액면분할 이후 기준 가격을 반영했다.",
                report_date=today - timedelta(days=index),
                published_at=timezone.now(),
                target_price=50000,
                previous_target_price=500000,
            )
            self.assertTrue(is_stock_split_adjustment(report))

        rule = AlertRule.objects.create(
            name="ignore-split",
            direction=AlertRule.DIRECTION_DOWN,
            min_revision_count=2,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        self.assertEqual(detect_signals(rule, sources=["naver"]), [])

    def test_ignores_common_split_ratio_even_without_keyword(self) -> None:
        security = Security.objects.create(symbol="234560", name="비율테스트", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Ratio Split Broker")
        report = ResearchReport.objects.create(
            source="naver",
            source_report_id="split-ratio",
            security=security,
            brokerage=brokerage,
            title="목표가 조정",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=102000,
            previous_target_price=1000000,
        )

        self.assertTrue(is_stock_split_adjustment(report))

    def test_ignores_reverse_split_adjusted_target_price_jump(self) -> None:
        security = Security.objects.create(symbol="345670", name="병합테스트", market="KOSPI")
        today = timezone.localdate()
        for index in range(2):
            brokerage = Brokerage.objects.create(name=f"Reverse Split Broker {index}")
            ResearchReport.objects.create(
                source="naver",
                source_report_id=f"reverse-split-{index}",
                security=security,
                brokerage=brokerage,
                title="액면병합 반영 목표가 조정",
                summary="주식병합 이후 기준 가격을 반영했다.",
                report_date=today - timedelta(days=index),
                published_at=timezone.now(),
                target_price=500000,
                previous_target_price=50000,
            )

        rule = AlertRule.objects.create(
            name="ignore-reverse-split",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=2,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        self.assertEqual(detect_signals(rule, sources=["naver"]), [])

    def test_ignores_capital_action_price_adjustments(self) -> None:
        security = Security.objects.create(symbol="456780", name="증자테스트", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Capital Action Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="capital-action",
            security=security,
            brokerage=brokerage,
            title="유상증자 권리락 반영",
            summary="신주 발행과 권리락을 반영해 목표가 기준을 조정했다.",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=70000,
            previous_target_price=100000,
        )

        rule = AlertRule.objects.create(
            name="ignore-capital-action",
            direction=AlertRule.DIRECTION_DOWN,
            min_revision_count=1,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        self.assertEqual(detect_signals(rule, sources=["naver"]), [])

    def test_ignores_reorganization_price_adjustments(self) -> None:
        security = Security.objects.create(symbol="567890", name="분할합병테스트", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Reorg Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="reorg-action",
            security=security,
            brokerage=brokerage,
            title="인적분할 및 지주회사 전환 반영",
            summary="기업분할 이후 비교 기준이 달라졌다.",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=60000,
            previous_target_price=90000,
        )

        rule = AlertRule.objects.create(
            name="ignore-reorg-action",
            direction=AlertRule.DIRECTION_DOWN,
            min_revision_count=1,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        self.assertEqual(detect_signals(rule, sources=["naver"]), [])

    def test_coverage_reset_does_not_link_previous_target_on_ingest(self) -> None:
        ingest_reports(
            [
                ParsedReport(
                    source="naver",
                    source_report_id="coverage-old",
                    symbol="678900",
                    security_name="커버리지테스트",
                    brokerage_name="Coverage Broker",
                    title="기존 리포트",
                    report_date=date(2026, 4, 1),
                    target_price=100000,
                ),
                ParsedReport(
                    source="naver",
                    source_report_id="coverage-reset",
                    symbol="678900",
                    security_name="커버리지테스트",
                    brokerage_name="Coverage Broker",
                    title="커버리지 재개",
                    summary="커버리지 재개로 신규 기준 목표가를 제시한다.",
                    report_date=date(2026, 5, 1),
                    target_price=130000,
                ),
            ]
        )

        report = ResearchReport.objects.get(source_report_id="coverage-reset")
        self.assertIsNone(report.previous_target_price)

    def test_attach_current_prices_adds_live_price_to_summary(self) -> None:
        security = Security.objects.create(symbol="005930", name="삼성전자", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Live Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="live-price-1",
            security=security,
            brokerage=brokerage,
            title="Live price test",
            summary="HBM 수요 확대로 실적 추정이 개선됐다.",
            opinion="매수",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=150000,
            previous_target_price=120000,
            eps_forecast=Decimal("6000"),
        )

        rule = AlertRule.objects.create(
            name="live-price",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=1,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        signal = detect_signals(rule, sources=["naver"])[0]
        attach_current_prices(
            [signal],
            {
                "005930": StockPriceSnapshot(
                    symbol="005930",
                    current_price=101000,
                    previous_close=100000,
                )
            },
        )

        self.assertIn("현재가: 101,000원", signal.summary)
        self.assertIn("참고 의견:", signal.summary)
        self.assertIn("매수", signal.summary)
        self.assertIn("최신 목표가: 150,000원", signal.summary)
        self.assertIn("신호 확인: 신뢰도", signal.summary)
        self.assertIn("점검 정상", signal.summary)
        self.assertIn("- 알림 유형:", signal.summary)
        self.assertIn("- 최근 주가 반응:", signal.summary)
        self.assertNotIn("EPS: N/A", signal.summary)
        self.assertLess(signal.summary.index("- 최근 주가 반응:"), signal.summary.index("🧪 EPS:"))
        self.assertLess(signal.summary.index("🧪 EPS:"), signal.summary.index("🤖 참고 의견:"))


class DigestTests(TestCase):
    def test_build_digest_message_shows_none_when_no_signal(self) -> None:
        rule = AlertRule.objects.create(
            name="digest-none",
            direction=AlertRule.DIRECTION_BOTH,
            min_revision_count=2,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        message = build_digest_message(
            region_label="국내",
            region_emoji="🇰🇷",
            rule=rule,
            signals=[],
            note="수집 0건 | 신규 0건 | 갱신 0건 | 즉시알림 0건",
        )
        self.assertIn("리비전 없음", message)

    def test_build_digest_message_includes_current_price_gap(self) -> None:
        security = Security.objects.create(symbol="005930", name="삼성전자", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Test Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="digest-price-1",
            security=security,
            brokerage=brokerage,
            title="HBM 모멘텀 반영",
            summary="HBM 수요 확대로 실적 추정이 개선됐다.",
            opinion="매수",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=150000,
            previous_target_price=120000,
            eps_forecast=Decimal("6000"),
        )
        rule = AlertRule.objects.create(
            name="digest-price",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=1,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )
        signal = detect_signals(rule, sources=["naver"])[0]
        message = build_digest_message(
            region_label="국내",
            region_emoji="🇰🇷",
            rule=rule,
            signals=[signal],
            price_snapshots={
                "005930": StockPriceSnapshot(
                    symbol="005930",
                    current_price=100000,
                    previous_close=99000,
                )
            },
        )
        self.assertIn("현재가 100,000원", message)
        self.assertIn("최신TP 150,000원", message)
        self.assertIn("괴리 +50.00%", message)
        self.assertIn("참고 의견", message)
        self.assertIn("신호 확인 신뢰도", message)
        self.assertIn("점검 정상", message)
        self.assertIn("🧾 요약:", message)
        self.assertIn("- 알림 유형", message)
        self.assertIn("- 최근 주가 반응", message)
        self.assertIn("최근 리포트 투자의견은 매수입니다.", message)
        self.assertNotIn("EPS N/A", message)
        self.assertNotIn("전일종가", message)
        self.assertLess(message.index("- 최근 주가 반응"), message.index("🧪 EPS:"))
        self.assertLess(message.index("🧪 EPS:"), message.index("🤖 참고 의견"))

    def test_matches_us_dst_mode(self) -> None:
        summer = datetime(2026, 7, 1, 10, 15, tzinfo=ZoneInfo("Asia/Seoul"))
        winter = datetime(2026, 1, 15, 11, 15, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertTrue(matches_us_dst_mode("dst", now=summer))
        self.assertFalse(matches_us_dst_mode("standard", now=summer))
        self.assertTrue(matches_us_dst_mode("standard", now=winter))


class OpinionEngineTests(TestCase):
    def test_buy_opinion_alone_stays_buy_not_strong_buy(self) -> None:
        security = Security.objects.create(symbol="005930", name="삼성전자", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Opinion Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="opinion-buy-1",
            security=security,
            brokerage=brokerage,
            title="보수적 테스트",
            summary="실적 기대는 유지되지만 추가 확인이 필요하다.",
            opinion="매수",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=120000,
            previous_target_price=110000,
        )

        rule = AlertRule.objects.create(
            name="opinion-buy",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=1,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        signal = detect_signals(rule, sources=["naver"])[0]
        assessment = assess_signal(signal, current_price=100000)

        self.assertEqual(assessment.label, "매수")

    def test_strong_buy_requires_multiple_objective_signals(self) -> None:
        security = Security.objects.create(symbol="000660", name="SK하이닉스", market="KOSPI")
        today = timezone.localdate()
        for index in range(3):
            brokerage = Brokerage.objects.create(name=f"Strong Broker {index}")
            ResearchReport.objects.create(
                source="naver",
                source_report_id=f"strong-buy-{index}",
                security=security,
                brokerage=brokerage,
                title=f"HBM strong {index}",
                summary="고대역폭 메모리 수요 확대가 실적 추정을 밀어올리고 있다.",
                opinion="매수",
                report_date=today - timedelta(days=index),
                published_at=timezone.now(),
                target_price=180000,
                previous_target_price=130000,
            )

        rule = AlertRule.objects.create(
            name="opinion-strong-buy",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=2,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
            distinct_brokerage_only=True,
        )

        signal = detect_signals(rule, sources=["naver"])[0]
        assessment = assess_signal(signal, current_price=100000)

        self.assertEqual(assessment.label, "적극매수")


class SignalAnalysisTests(TestCase):
    def test_flags_suspicious_target_price_against_current_price(self) -> None:
        security = Security.objects.create(symbol="900001", name="파싱테스트", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Parsing Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="suspicious-target",
            security=security,
            brokerage=brokerage,
            title="목표가 파싱 테스트",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=900000,
            previous_target_price=100000,
        )
        rule = AlertRule.objects.create(
            name="suspicious-target",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=1,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        signal = detect_signals(rule, sources=["naver"])[0]
        analysis = analyze_signal(signal, current_price=100000, previous_close=99000)

        self.assertEqual(analysis.signal_check_label, "검토 필요")
        self.assertEqual(analysis.reliability_label, "낮음")
        self.assertIn("전일 대비 +1.01%", analysis.price_reaction_line)

    def test_eps_direction_is_shown_when_previous_eps_exists(self) -> None:
        security = Security.objects.create(symbol="900002", name="EPS테스트", market="KOSPI")
        brokerage = Brokerage.objects.create(name="EPS Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="eps-old",
            security=security,
            brokerage=brokerage,
            title="이전 EPS",
            report_date=timezone.localdate() - timedelta(days=4),
            published_at=timezone.now(),
            target_price=100000,
            previous_target_price=95000,
            eps_forecast=Decimal("5000"),
        )
        ResearchReport.objects.create(
            source="naver",
            source_report_id="eps-new",
            security=security,
            brokerage=brokerage,
            title="신규 EPS",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=130000,
            previous_target_price=100000,
            eps_forecast=Decimal("6000"),
        )
        rule = AlertRule.objects.create(
            name="eps-trend",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=1,
            lookback_days=7,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("9999.00"),
        )

        signal = detect_signals(rule, sources=["naver"])[0]
        analysis = analyze_signal(signal, current_price=100000)

        self.assertIn("5,000.00 -> 6,000.00 (+20.00%)", analysis.eps_line)


class TelegramMessageTests(TestCase):
    def test_chunk_message_splits_long_digest_on_sections(self) -> None:
        message = "\n\n".join(f"section {index} " + ("x" * 200) for index in range(10))

        chunks = chunk_message(message, limit=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))


class WatchlistImportCommandTests(TestCase):
    def test_import_watchlist_csv_creates_entries(self) -> None:
        csv_path = Path(settings.BASE_DIR) / "data" / "examples" / "watchlist.sample.csv"
        call_command("import_watchlist_csv", str(csv_path))

        security = Security.objects.get(symbol="005930")
        entry = WatchlistEntry.objects.get(security=security)
        self.assertEqual(entry.priority, 1)
        self.assertTrue(entry.enabled)


class AlertRuleCommandTests(TestCase):
    def test_upsert_alert_rule_creates_rule(self) -> None:
        call_command(
            "upsert_alert_rule",
            "watchlist-up",
            "--direction",
            "up",
            "--min-count",
            "4",
            "--lookback-days",
            "7",
            "--watchlist-only",
        )

        rule = AlertRule.objects.get(name="watchlist-up")
        self.assertEqual(rule.direction, "up")
        self.assertEqual(rule.min_revision_count, 4)
        self.assertTrue(rule.watchlist_only)

    def test_observation_alert_uses_one_large_revision_before_confirmation(self) -> None:
        security = Security.objects.create(symbol="777770", name="관찰테스트", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Observation Broker")
        ResearchReport.objects.create(
            source="naver",
            source_report_id="observation-large",
            security=security,
            brokerage=brokerage,
            title="큰 폭 목표가 상향",
            report_date=timezone.localdate(),
            published_at=timezone.now(),
            target_price=130000,
            previous_target_price=100000,
        )
        observation_rule = ensure_observation_rule()

        result = run_alert_cycle(
            sources=["naver"],
            rule_names=[observation_rule.name],
            max_distinct_brokerage_count=1,
            message_prefix="선행 관찰 알림",
        )

        self.assertEqual(result["created_events"], 1)
        self.assertEqual(security.alert_events.count(), 1)
        self.assertIn("선행 관찰 알림", security.alert_events.first().summary)
