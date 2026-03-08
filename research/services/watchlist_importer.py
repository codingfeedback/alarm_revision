from __future__ import annotations

import csv
from pathlib import Path

from research.models import Security, WatchlistEntry


def _to_bool(value: str, default: bool = True) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "y", "on"}


def _to_int(value: str, default: int = 3) -> int:
    value = value.strip()
    if not value:
        return default
    return int(value)


def import_watchlist_rows(csv_path: Path, disable_missing: bool = False) -> dict[str, int]:
    created = 0
    updated = 0
    seen_symbols: set[str] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            symbol = row.get("symbol", "").strip().replace("A", "")
            if not symbol:
                continue
            seen_symbols.add(symbol)

            security, security_created = Security.objects.get_or_create(
                symbol=symbol,
                defaults={
                    "name": row.get("security_name", "").strip() or symbol,
                    "market": row.get("market", "").strip(),
                },
            )
            if not security_created:
                next_name = row.get("security_name", "").strip()
                next_market = row.get("market", "").strip()
                dirty = False
                if next_name and security.name != next_name:
                    security.name = next_name
                    dirty = True
                if next_market and security.market != next_market:
                    security.market = next_market
                    dirty = True
                if dirty:
                    security.save(update_fields=["name", "market", "updated_at"])

            _, was_created = WatchlistEntry.objects.update_or_create(
                security=security,
                defaults={
                    "priority": _to_int(row.get("priority", ""), default=3),
                    "enabled": _to_bool(row.get("enabled", ""), default=True),
                    "notes": row.get("notes", "").strip(),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    disabled = 0
    if disable_missing and seen_symbols:
        queryset = WatchlistEntry.objects.exclude(security__symbol__in=seen_symbols).filter(enabled=True)
        disabled = queryset.update(enabled=False)

    return {"created": created, "updated": updated, "disabled": disabled}
