from __future__ import annotations

from django.db import models

from research.models import Security


class AlertRule(models.Model):
    DIRECTION_UP = "up"
    DIRECTION_DOWN = "down"
    DIRECTION_BOTH = "both"
    DIRECTION_CHOICES = [
        (DIRECTION_UP, "Up"),
        (DIRECTION_DOWN, "Down"),
        (DIRECTION_BOTH, "Both"),
    ]

    name = models.CharField(max_length=100, unique=True)
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default=DIRECTION_BOTH,
    )
    min_revision_count = models.PositiveSmallIntegerField(default=3)
    lookback_days = models.PositiveSmallIntegerField(default=5)
    min_revision_ratio = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    immediate_revision_ratio = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=20,
    )
    distinct_brokerage_only = models.BooleanField(default=True)
    watchlist_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AlertEvent(models.Model):
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="events")
    security = models.ForeignKey(Security, on_delete=models.CASCADE, related_name="alert_events")
    direction = models.CharField(max_length=10, choices=AlertRule.DIRECTION_CHOICES)
    revision_count = models.PositiveSmallIntegerField(default=0)
    distinct_brokerage_count = models.PositiveSmallIntegerField(default=0)
    average_revision_ratio = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    max_revision_ratio = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    summary = models.TextField()
    dedupe_key = models.CharField(max_length=64, unique=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    triggered_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-triggered_at"]

    def __str__(self) -> str:
        return f"{self.security.symbol} {self.direction} {self.triggered_at:%Y-%m-%d %H:%M}"
