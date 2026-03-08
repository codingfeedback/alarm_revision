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
from alerts.services.revision_detector import detect_signals
from research.models import Brokerage, ResearchReport, Security, WatchlistEntry
from research.services.naver_quotes import StockPriceSnapshot


class RevisionDetectorTests(TestCase):
    def test_detects_two_upward_revisions(self) -> None:
        security = Security.objects.create(symbol="035420", name="NAVER", market="KOSPI")
        today = date(2026, 3, 7)
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
        today = date(2026, 3, 7)
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
            report_date=date(2026, 3, 7),
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

    def test_build_digest_message_includes_previous_close_gap(self) -> None:
        security = Security.objects.create(symbol="005930", name="삼성전자", market="KOSPI")
        brokerage = Brokerage.objects.create(name="Test Broker")
        report = ResearchReport.objects.create(
            source="naver",
            source_report_id="digest-price-1",
            security=security,
            brokerage=brokerage,
            title="HBM 모멘텀 반영",
            summary="HBM 수요 확대로 실적 추정이 개선됐다.",
            report_date=date(2026, 3, 7),
            published_at=timezone.now(),
            target_price=150000,
            previous_target_price=120000,
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
                    current_price=101000,
                    previous_close=100000,
                )
            },
        )
        self.assertIn("전일종가 100,000원", message)
        self.assertIn("최신TP 150,000원", message)
        self.assertIn("괴리 +50.00%", message)

    def test_matches_us_dst_mode(self) -> None:
        summer = datetime(2026, 7, 1, 10, 15, tzinfo=ZoneInfo("Asia/Seoul"))
        winter = datetime(2026, 1, 15, 11, 15, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertTrue(matches_us_dst_mode("dst", now=summer))
        self.assertFalse(matches_us_dst_mode("standard", now=summer))
        self.assertTrue(matches_us_dst_mode("standard", now=winter))


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
