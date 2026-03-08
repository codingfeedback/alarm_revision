from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from alerts.services.orchestrator import ensure_default_rule
from research.models import Brokerage, ResearchReport, Security, WatchlistEntry


class Command(BaseCommand):
    help = "Create sample securities, reports, and a default alert rule."

    def handle(self, *args, **options):
        security, _ = Security.objects.get_or_create(
            symbol="005930",
            defaults={"name": "Samsung Electronics", "market": "KOSPI"},
        )
        WatchlistEntry.objects.get_or_create(security=security, defaults={"priority": 1})

        for index, brokerage_name in enumerate(
            ["Mirae Asset", "NH Investment", "Kiwoom"]
        ):
            brokerage, _ = Brokerage.objects.get_or_create(name=brokerage_name)
            ResearchReport.objects.update_or_create(
                source="manual",
                source_report_id=f"demo-{index}",
                defaults={
                    "security": security,
                    "brokerage": brokerage,
                    "title": f"Demo revision {index}",
                    "report_date": timezone.localdate() - timedelta(days=index),
                    "published_at": timezone.now() - timedelta(hours=index),
                    "target_price": 110000 + (index * 5000),
                    "previous_target_price": 100000,
                    "summary": "Demo data for initial validation.",
                },
            )

        ensure_default_rule()
        self.stdout.write(self.style.SUCCESS("Demo data and default rule are ready."))
