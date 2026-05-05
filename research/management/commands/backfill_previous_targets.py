from django.core.management.base import BaseCommand

from research.models import ResearchReport
from research.services.report_flags import should_skip_previous_target_link


class Command(BaseCommand):
    help = "Backfill previous target prices by matching older reports from the same brokerage and security."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--source", default="naver")
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options):
        queryset = (
            ResearchReport.objects.select_related("security", "brokerage")
            .filter(source=options["source"])
            .exclude(target_price__isnull=True)
            .order_by("security_id", "brokerage_id", "report_date", "id")
        )

        last_target_by_key: dict[tuple[int, int], int] = {}
        updated = 0
        for report in queryset:
            key = (report.security_id, report.brokerage_id)
            previous_target = last_target_by_key.get(key)
            if should_skip_previous_target_link(report):
                last_target_by_key[key] = report.target_price
                continue
            should_update = options["overwrite"] or report.previous_target_price is None
            if should_update and previous_target is not None and report.previous_target_price != previous_target:
                report.previous_target_price = previous_target
                report.save(update_fields=["previous_target_price", "updated_at"])
                updated += 1
            last_target_by_key[key] = report.target_price

        self.stdout.write(self.style.SUCCESS(f"previous target backfill updated={updated}"))
