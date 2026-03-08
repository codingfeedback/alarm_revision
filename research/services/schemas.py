from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(slots=True)
class ParsedReport:
    source: str
    source_report_id: str
    symbol: str
    security_name: str
    market: str = ""
    brokerage_name: str = ""
    brokerage_code: str = ""
    analyst_name: str = ""
    title: str = ""
    report_date: date | None = None
    published_at: datetime | None = None
    target_price: int | None = None
    previous_target_price: int | None = None
    eps_forecast: Decimal | None = None
    opinion: str = ""
    report_url: str = ""
    summary: str = ""
    raw_payload: dict = field(default_factory=dict)
