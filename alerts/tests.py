from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from alerts.models import AlertRule
from alerts.services.revision_detector import detect_signals
from research.models import Brokerage, ResearchReport, Security, WatchlistEntry


class RevisionDetectorTests(TestCase):
    def test_detects_three_upward_revisions(self) -> None:
        security = Security.objects.create(symbol="035420", name="NAVER")
        today = date(2026, 3, 7)
        for index in range(3):
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
            name="3x-up",
            direction=AlertRule.DIRECTION_UP,
            min_revision_count=3,
            lookback_days=5,
            min_revision_ratio=Decimal("0.00"),
            immediate_revision_ratio=Decimal("20.00"),
        )

        signals = detect_signals(rule)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].security.symbol, "035420")

    def test_ignores_zero_revision_ratio(self) -> None:
        security = Security.objects.create(symbol="271560", name="오리온")
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
            immediate_revision_ratio=Decimal("20.00"),
        )

        self.assertEqual(detect_signals(rule), [])


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
