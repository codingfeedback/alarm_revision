from django.core.management.base import BaseCommand

from alerts.services.orchestrator import run_alert_cycle


class Command(BaseCommand):
    help = "Detect revision signals and send Telegram alerts."

    def handle(self, *args, **options):
        result = run_alert_cycle()
        self.stdout.write(
            self.style.SUCCESS(
                f"created_events={result['created_events']} sent_events={result['sent_events']}"
            )
        )
