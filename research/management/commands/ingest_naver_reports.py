from django.core.management.base import BaseCommand

from research.services.ingestion import ingest_reports
from research.services.naver import NaverResearchCollector


class Command(BaseCommand):
    help = "Fetch and ingest recent research reports from Naver Research."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--pages", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--save-html", action="store_true")

    def handle(self, *args, **options):
        collector = NaverResearchCollector()
        all_reports = []

        for page in range(1, options["pages"] + 1):
            html = collector.fetch_listing_html(page=page)
            if options["save_html"]:
                snapshot_path = collector.save_snapshot(html, page)
                self.stdout.write(f"saved snapshot: {snapshot_path}")
            parsed = collector.parse_listing(html)
            self.stdout.write(f"page={page} parsed={len(parsed)}")
            all_reports.extend(parsed)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run complete. DB not modified."))
            return

        created, updated = ingest_reports(all_reports)
        self.stdout.write(
            self.style.SUCCESS(
                f"ingested reports={len(all_reports)} created={created} updated={updated}"
            )
        )
