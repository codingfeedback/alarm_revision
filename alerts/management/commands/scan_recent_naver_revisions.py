import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from research.models import ResearchReport


class Command(BaseCommand):
    help = "Scan recent Naver revision cases from stored reports."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--lookback-days", type=int, default=14)
        parser.add_argument("--min-count", type=int, default=3)
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--direction", choices=["up", "down", "both"], default="both")

    def handle(self, *args, **options):
        start_date = timezone.localdate() - timedelta(days=options["lookback_days"])
        reports = (
            ResearchReport.objects.select_related("security", "brokerage")
            .filter(source="naver", report_date__gte=start_date)
            .exclude(target_price__isnull=True)
            .exclude(previous_target_price__isnull=True)
            .order_by("-report_date")
        )

        grouped: dict[tuple[str, str, str], list[ResearchReport]] = {}
        for report in reports:
            ratio = report.revision_ratio
            if ratio is None or ratio == 0:
                continue
            direction = "up" if ratio > 0 else "down"
            if options["direction"] != "both" and options["direction"] != direction:
                continue
            grouped.setdefault((report.security.symbol, report.security.name, direction), []).append(report)

        hits = []
        for key, rows in grouped.items():
            brokerage_count = len({row.brokerage.name for row in rows})
            if brokerage_count < options["min_count"]:
                continue
            hits.append(
                {
                    "symbol": key[0],
                    "name": key[1],
                    "direction": key[2],
                    "brokerage_count": brokerage_count,
                    "report_count": len(rows),
                    "reports": [
                        {
                            "date": row.report_date.isoformat(),
                            "brokerage": row.brokerage.name,
                            "title": row.title,
                            "previous_target_price": row.previous_target_price,
                            "target_price": row.target_price,
                            "revision_ratio": str(row.revision_ratio),
                            "report_url": row.report_url,
                        }
                        for row in rows
                    ],
                }
            )

        hits.sort(
            key=lambda item: (
                item["brokerage_count"],
                item["report_count"],
                max(float(report["revision_ratio"]) for report in item["reports"]),
            ),
            reverse=True,
        )
        trimmed = hits[: options["limit"]]
        self.stdout.write(json.dumps(trimmed, ensure_ascii=False, indent=2))
