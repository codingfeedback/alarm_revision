from __future__ import annotations

from django.db import IntegrityError
from django.utils import timezone

from alerts.models import AlertEvent, AlertRule
from alerts.services.revision_detector import detect_signals
from alerts.services.telegram import TelegramNotifier


def ensure_default_rule() -> AlertRule:
    from django.conf import settings

    rule, _ = AlertRule.objects.update_or_create(
        name=settings.DEFAULT_ALERT_RULE_NAME,
        defaults={
            "direction": AlertRule.DIRECTION_BOTH,
            "min_revision_count": settings.DEFAULT_MIN_REVISION_COUNT,
            "lookback_days": settings.DEFAULT_LOOKBACK_DAYS,
            "min_revision_ratio": settings.DEFAULT_MIN_REVISION_RATIO,
            "immediate_revision_ratio": settings.DEFAULT_IMMEDIATE_REVISION_RATIO,
            "watchlist_only": settings.DEFAULT_WATCHLIST_ONLY,
            "distinct_brokerage_only": True,
            "is_active": True,
        },
    )
    return rule


def run_alert_cycle() -> dict[str, int]:
    ensure_default_rule()

    created_events = 0
    sent_events = 0
    notifier = TelegramNotifier()

    for rule in AlertRule.objects.filter(is_active=True):
        for signal in detect_signals(rule):
            try:
                event = AlertEvent.objects.create(
                    rule=rule,
                    security=signal.security,
                    direction=signal.direction,
                    revision_count=signal.revision_count,
                    distinct_brokerage_count=signal.distinct_brokerage_count,
                    average_revision_ratio=signal.average_revision_ratio,
                    max_revision_ratio=signal.max_revision_ratio,
                    summary=signal.summary,
                    dedupe_key=signal.dedupe_key,
                    raw_payload=signal.raw_payload,
                )
                created_events += 1
            except IntegrityError:
                continue

            if notifier.is_configured():
                try:
                    notifier.send_message(signal.summary)
                    event.delivered_at = timezone.now()
                    event.save(update_fields=["delivered_at"])
                    sent_events += 1
                except Exception as exc:  # noqa: BLE001
                    event.delivery_error = str(exc)
                    event.save(update_fields=["delivery_error"])

    return {"created_events": created_events, "sent_events": sent_events}
