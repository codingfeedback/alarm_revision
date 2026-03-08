from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from research.services.csv_importer import load_reports_from_csv
from research.services.ingestion import ingest_reports


class Command(BaseCommand):
    help = "Import research reports from a CSV file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).resolve()
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        reports = load_reports_from_csv(csv_path)
        created, updated = ingest_reports(reports)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(reports)} rows. created={created}, updated={updated}"
            )
        )
