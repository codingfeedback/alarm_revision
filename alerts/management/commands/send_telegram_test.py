from django.core.management.base import BaseCommand, CommandError

from alerts.services.telegram import TelegramNotifier


class Command(BaseCommand):
    help = "Send a test Telegram message using current .env settings."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--message", type=str, default="증권사 개정 알람 텔레그램 테스트 메시지")

    def handle(self, *args, **options):
        notifier = TelegramNotifier()
        if not notifier.is_configured():
            raise CommandError("Telegram is not configured. Check .env values.")
        notifier.send_message(options["message"])
        self.stdout.write(self.style.SUCCESS("telegram test sent"))
