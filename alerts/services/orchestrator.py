from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError
from django.utils import timezone

from alerts.models import AlertEvent, AlertRule
from alerts.services.revision_detector import attach_current_prices, detect_signals
from alerts.services.telegram import TelegramNotifier
from research.services.naver_quotes import NaverQuoteCollector


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


def ensure_observation_rule() -> AlertRule:
    from django.conf import settings

    rule, _ = AlertRule.objects.update_or_create(
        name=settings.OBSERVATION_ALERT_RULE_NAME,
        defaults={
            "direction": AlertRule.DIRECTION_BOTH,
            "min_revision_count": 1,
            "lookback_days": settings.DEFAULT_LOOKBACK_DAYS,
            "min_revision_ratio": settings.OBSERVATION_MIN_REVISION_RATIO,
            "immediate_revision_ratio": Decimal("9999.00"),
            "watchlist_only": settings.DEFAULT_WATCHLIST_ONLY,
            "distinct_brokerage_only": True,
            "is_active": True,
        },
    )
    return rule


def run_alert_cycle(
    sources: list[str] | None = None,
    rule_names: list[str] | None = None,
    max_distinct_brokerage_count: int | None = None,
    message_prefix: str = "",
) -> dict[str, int]:
    ensure_default_rule()
    observation_rule = ensure_observation_rule()

    created_events = 0
    sent_events = 0
    notifier = TelegramNotifier()
    quote_collector = NaverQuoteCollector()
    rules = AlertRule.objects.filter(is_active=True)
    if rule_names:
        rules = rules.filter(name__in=rule_names)
    else:
        rules = rules.exclude(name=observation_rule.name)

    for rule in rules:
        signals = detect_signals(rule, sources=sources)
        if max_distinct_brokerage_count is not None:
            signals = [
                signal
                for signal in signals
                if signal.distinct_brokerage_count <= max_distinct_brokerage_count
            ]
        if sources and "naver" in sources:
            snapshots = quote_collector.fetch_snapshots(
                [signal.security.symbol for signal in signals]
            )
            signals = attach_current_prices(signals, snapshots)
        for signal in signals:
            message = f"{message_prefix}\n\n{signal.summary}" if message_prefix else signal.summary
            try:
                event = AlertEvent.objects.create(
                    rule=rule,
                    security=signal.security,
                    direction=signal.direction,
                    revision_count=signal.revision_count,
                    distinct_brokerage_count=signal.distinct_brokerage_count,
                    average_revision_ratio=signal.average_revision_ratio,
                    max_revision_ratio=signal.max_revision_ratio,
                    summary=message,
                    dedupe_key=signal.dedupe_key,
                    raw_payload=signal.raw_payload,
                )
                created_events += 1
            except IntegrityError:
                continue

            if notifier.is_configured():
                try:
                    notifier.send_message(message)
                    event.delivered_at = timezone.now()
                    event.save(update_fields=["delivered_at"])
                    sent_events += 1
                except Exception as exc:  # noqa: BLE001
                    event.delivery_error = str(exc)
                    event.save(update_fields=["delivery_error"])

    return {"created_events": created_events, "sent_events": sent_events}
