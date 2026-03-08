from django.contrib import admin

from alerts.models import AlertEvent, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "direction",
        "min_revision_count",
        "lookback_days",
        "watchlist_only",
        "is_active",
    )
    list_filter = ("direction", "watchlist_only", "is_active")


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = (
        "security",
        "rule",
        "direction",
        "revision_count",
        "triggered_at",
        "delivered_at",
    )
    list_filter = ("direction", "triggered_at", "delivered_at")
    search_fields = ("security__name", "security__symbol", "summary")
