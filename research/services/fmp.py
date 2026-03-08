from __future__ import annotations

import hashlib
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from research.services.schemas import ParsedReport


class FMPResearchCollector:
    price_target_url = "https://financialmodelingprep.com/api/v4/price-target"

    def __init__(
        self,
        api_key: str | None = None,
        tickers: list[str] | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.OVERSEAS_FMP_API_KEY
        self.tickers = tickers or settings.OVERSEAS_TICKERS
        self.timeout = timeout or settings.RESEARCH_REQUEST_TIMEOUT

    def is_configured(self) -> bool:
        return bool(self.api_key and self.tickers)

    def fetch_reports(self, per_symbol_limit: int | None = None) -> list[ParsedReport]:
        if not self.is_configured():
            return []

        reports: list[ParsedReport] = []
        limit = per_symbol_limit or settings.OVERSEAS_PRICE_TARGET_LIMIT
        for symbol in self.tickers:
            reports.extend(self.fetch_symbol_reports(symbol=symbol, limit=limit))
        return reports

    def fetch_symbol_reports(self, symbol: str, limit: int) -> list[ParsedReport]:
        response = requests.get(
            self.price_target_url,
            params={"symbol": symbol, "apikey": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []

        reports: list[ParsedReport] = []
        for row in payload[:limit]:
            target_price = _to_int(row.get("priceTarget") or row.get("targetPrice"))
            published_at = _parse_datetime(row.get("publishedDate") or row.get("date"))
            report_date = published_at.date() if published_at else None
            if target_price is None or report_date is None:
                continue

            brokerage_name = (
                row.get("analystCompany")
                or row.get("newsPublisher")
                or row.get("publisher")
                or "Unknown Brokerage"
            )
            analyst_name = row.get("analystName") or ""
            title = row.get("newsTitle") or row.get("title") or f"{symbol} target update"
            report_url = row.get("newsURL") or row.get("url") or ""
            security_name = row.get("symbol") or symbol
            source_report_id = hashlib.sha1(
                (
                    f"{symbol}|{brokerage_name}|{analyst_name}|{published_at.isoformat()}|"
                    f"{target_price}|{report_url}"
                ).encode("utf-8")
            ).hexdigest()
            summary = row.get("newsTitle") or row.get("newsText") or ""

            reports.append(
                ParsedReport(
                    source="fmp",
                    source_report_id=source_report_id,
                    symbol=symbol,
                    security_name=security_name,
                    market="US",
                    brokerage_name=brokerage_name,
                    analyst_name=analyst_name,
                    title=title,
                    report_date=report_date,
                    published_at=published_at,
                    target_price=target_price,
                    opinion=(row.get("adjRating") or row.get("rating_current") or "").strip(),
                    report_url=report_url,
                    summary=summary,
                    raw_payload=row,
                )
            )

        return reports


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return timezone.make_aware(parsed, dt_timezone.utc)
    return parsed.astimezone(dt_timezone.utc)


def _to_int(value) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(Decimal(str(value)))
    except Exception:  # noqa: BLE001
        return None
