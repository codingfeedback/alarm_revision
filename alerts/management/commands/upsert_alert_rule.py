from django.core.management.base import BaseCommand

from alerts.models import AlertRule


class Command(BaseCommand):
    help = "Create or update an alert rule from command arguments."

    def add_arguments(self, parser) -> None:
        parser.add_argument("name", type=str)
        parser.add_argument("--direction", choices=["up", "down", "both"], default="both")
        parser.add_argument("--min-count", type=int, default=3)
        parser.add_argument("--lookback-days", type=int, default=5)
        parser.add_argument("--min-ratio", type=float, default=0)
        parser.add_argument("--immediate-ratio", type=float, default=20)
        parser.add_argument("--watchlist-only", action="store_true")
        parser.add_argument("--all-stocks", action="store_true")
        parser.add_argument("--allow-same-brokerage", action="store_true")
        parser.add_argument("--inactive", action="store_true")

    def handle(self, *args, **options):
        watchlist_only = options["watchlist_only"] and not options["all_stocks"]
        rule, created = AlertRule.objects.update_or_create(
            name=options["name"],
            defaults={
                "direction": options["direction"],
                "min_revision_count": options["min_count"],
                "lookback_days": options["lookback_days"],
                "min_revision_ratio": options["min_ratio"],
                "immediate_revision_ratio": options["immediate_ratio"],
                "watchlist_only": watchlist_only,
                "distinct_brokerage_only": not options["allow_same_brokerage"],
                "is_active": not options["inactive"],
            },
        )
        verb = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"rule {verb}: {rule.name}"))
