from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.utils import timezone

from research.services.schemas import ParsedReport


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def _parse_int(value: str) -> int | None:
    value = value.replace(",", "").strip()
    if not value:
        return None
    return int(value)


def _parse_decimal(value: str) -> Decimal | None:
    value = value.replace(",", "").strip()
    if not value:
        return None
    return Decimal(value)


def load_reports_from_csv(csv_path: Path) -> list[ParsedReport]:
    rows: list[ParsedReport] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for index, row in enumerate(reader, start=1):
            source = row.get("source", "csv").strip() or "csv"
            source_report_id = row.get("source_report_id", "").strip() or f"csv-{index}"
            rows.append(
                ParsedReport(
                    source=source,
                    source_report_id=source_report_id,
                    symbol=row.get("symbol", "").strip(),
                    security_name=row.get("security_name", "").strip(),
                    market=row.get("market", "").strip(),
                    brokerage_name=row.get("brokerage_name", "").strip(),
                    brokerage_code=row.get("brokerage_code", "").strip(),
                    analyst_name=row.get("analyst_name", "").strip(),
                    title=row.get("title", "").strip(),
                    report_date=_parse_date(row.get("report_date", "")),
                    published_at=_parse_datetime(row.get("published_at", "")),
                    target_price=_parse_int(row.get("target_price", "")),
                    previous_target_price=_parse_int(row.get("previous_target_price", "")),
                    eps_forecast=_parse_decimal(row.get("eps_forecast", "")),
                    opinion=row.get("opinion", "").strip(),
                    report_url=row.get("report_url", "").strip(),
                    summary=row.get("summary", "").strip(),
                    raw_payload={"csv_row": row},
                )
            )
    return rows
