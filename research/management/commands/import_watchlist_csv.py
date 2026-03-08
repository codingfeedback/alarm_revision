from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from research.services.watchlist_importer import import_watchlist_rows


class Command(BaseCommand):
    help = "Import or update watchlist entries from a CSV file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("csv_path", type=str)
        parser.add_argument("--disable-missing", action="store_true")

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).resolve()
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        result = import_watchlist_rows(
            csv_path=csv_path,
            disable_missing=options["disable_missing"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "watchlist imported "
                f"created={result['created']} updated={result['updated']} disabled={result['disabled']}"
            )
        )
