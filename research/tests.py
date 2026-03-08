from datetime import date
from decimal import Decimal

from django.test import TestCase

from research.models import Brokerage, ResearchReport, Security


class ResearchReportModelTests(TestCase):
    def test_revision_ratio_is_computed(self) -> None:
        security = Security.objects.create(symbol="005930", name="Samsung Electronics")
        brokerage = Brokerage.objects.create(name="Test Securities")
        report = ResearchReport.objects.create(
            source="manual",
            source_report_id="manual-1",
            security=security,
            brokerage=brokerage,
            title="Test",
            report_date=date(2026, 3, 7),
            target_price=120000,
            previous_target_price=100000,
        )

        self.assertEqual(report.revision_ratio, Decimal("20.00"))
