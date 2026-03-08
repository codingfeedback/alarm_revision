from __future__ import annotations

from decimal import Decimal

from django.db import models


class Security(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    market = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]

    def __str__(self) -> str:
        return f"{self.symbol} {self.name}"


class WatchlistEntry(models.Model):
    security = models.OneToOneField(Security, on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=3)
    notes = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "security__symbol"]
        verbose_name = "Watchlist Entry"
        verbose_name_plural = "Watchlist Entries"

    def __str__(self) -> str:
        return f"{self.security.symbol} ({self.priority})"


class Brokerage(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Analyst(models.Model):
    brokerage = models.ForeignKey(
        Brokerage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analysts",
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["brokerage", "name"],
                name="unique_analyst_per_brokerage",
            )
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ResearchReport(models.Model):
    SOURCE_CHOICES = [
        ("naver", "Naver Research"),
        ("fmp", "Financial Modeling Prep"),
        ("csv", "CSV Import"),
        ("manual", "Manual"),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    source_report_id = models.CharField(max_length=120, blank=True)
    security = models.ForeignKey(
        Security,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    brokerage = models.ForeignKey(
        Brokerage,
        on_delete=models.PROTECT,
        related_name="reports",
    )
    analyst = models.ForeignKey(
        Analyst,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    title = models.CharField(max_length=255)
    report_date = models.DateField()
    published_at = models.DateTimeField(null=True, blank=True)
    target_price = models.BigIntegerField(null=True, blank=True)
    previous_target_price = models.BigIntegerField(null=True, blank=True)
    eps_forecast = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )
    opinion = models.CharField(max_length=50, blank=True)
    report_url = models.URLField(blank=True)
    summary = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_report_id"],
                name="unique_source_report_id",
                condition=~models.Q(source_report_id=""),
            )
        ]
        indexes = [
            models.Index(fields=["security", "report_date"]),
            models.Index(fields=["brokerage", "report_date"]),
            models.Index(fields=["published_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.security.symbol} {self.brokerage.name} {self.report_date}"

    @property
    def revision_ratio(self) -> Decimal | None:
        if not self.target_price or not self.previous_target_price:
            return None
        if self.previous_target_price == 0:
            return None
        return (
            (Decimal(self.target_price) - Decimal(self.previous_target_price))
            / Decimal(self.previous_target_price)
            * Decimal("100")
        ).quantize(Decimal("0.01"))
