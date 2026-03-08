from django.contrib import admin

from research.models import Analyst, Brokerage, ResearchReport, Security, WatchlistEntry


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "market", "is_active")
    list_filter = ("market", "is_active")
    search_fields = ("symbol", "name")


@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = ("security", "priority", "enabled", "created_at")
    list_filter = ("enabled",)


@admin.register(Brokerage)
class BrokerageAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")


@admin.register(Analyst)
class AnalystAdmin(admin.ModelAdmin):
    list_display = ("name", "brokerage")
    search_fields = ("name", "brokerage__name")


@admin.register(ResearchReport)
class ResearchReportAdmin(admin.ModelAdmin):
    list_display = (
        "security",
        "brokerage",
        "report_date",
        "target_price",
        "previous_target_price",
        "source",
    )
    list_filter = ("source", "report_date", "brokerage")
    search_fields = ("title", "security__name", "security__symbol", "brokerage__name")
