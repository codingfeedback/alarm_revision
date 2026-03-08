from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction

from research.models import Analyst, Brokerage, ResearchReport, Security
from research.services.schemas import ParsedReport


def _normalize_symbol(value: str) -> str:
    return value.strip().replace("A", "")


def _resolve_previous_target(
    item: ParsedReport,
    security: Security,
    brokerage: Brokerage,
) -> int | None:
    if item.previous_target_price:
        return item.previous_target_price
    if not item.report_date:
        return None

    previous_report = (
        ResearchReport.objects.filter(
            security=security,
            brokerage=brokerage,
            report_date__lt=item.report_date,
        )
        .exclude(target_price__isnull=True)
        .order_by("-report_date", "-created_at")
        .first()
    )
    if previous_report is None:
        return None
    return previous_report.target_price


@transaction.atomic
def ingest_reports(reports: Iterable[ParsedReport]) -> tuple[int, int]:
    created = 0
    updated = 0

    for item in reports:
        security, _ = Security.objects.get_or_create(
            symbol=_normalize_symbol(item.symbol),
            defaults={
                "name": item.security_name.strip(),
                "market": item.market.strip(),
            },
        )
        if item.security_name and security.name != item.security_name.strip():
            security.name = item.security_name.strip()
            security.market = item.market.strip()
            security.save(update_fields=["name", "market", "updated_at"])

        brokerage, _ = Brokerage.objects.get_or_create(
            name=item.brokerage_name.strip() or "Unknown Brokerage",
            defaults={"code": item.brokerage_code.strip()},
        )

        analyst = None
        if item.analyst_name.strip():
            analyst, _ = Analyst.objects.get_or_create(
                brokerage=brokerage,
                name=item.analyst_name.strip(),
            )

        previous_target_price = _resolve_previous_target(item, security, brokerage)
        defaults = {
            "security": security,
            "brokerage": brokerage,
            "analyst": analyst,
            "title": item.title.strip() or f"{security.name} report",
            "report_date": item.report_date,
            "published_at": item.published_at,
            "target_price": item.target_price,
            "previous_target_price": previous_target_price,
            "eps_forecast": item.eps_forecast,
            "opinion": item.opinion.strip(),
            "report_url": item.report_url.strip(),
            "summary": item.summary.strip(),
            "raw_payload": item.raw_payload,
        }

        report, is_created = ResearchReport.objects.update_or_create(
            source=item.source,
            source_report_id=item.source_report_id,
            defaults=defaults,
        )
        if is_created:
            created += 1
        else:
            updated += 1
            if not report.previous_target_price and previous_target_price:
                report.previous_target_price = previous_target_price
                report.save(update_fields=["previous_target_price", "updated_at"])

    return created, updated
