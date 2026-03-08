from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from alerts.models import AlertRule
from research.models import ResearchReport, Security, WatchlistEntry


@dataclass(slots=True)
class RevisionSignal:
    security: Security
    direction: str
    reports: list[ResearchReport]
    revision_count: int
    distinct_brokerage_count: int
    average_revision_ratio: Decimal | None
    max_revision_ratio: Decimal | None
    dedupe_key: str
    summary: str
    raw_payload: dict


def detect_signals(rule: AlertRule) -> list[RevisionSignal]:
    window_start = timezone.localdate() - timedelta(days=rule.lookback_days)
    reports = (
        ResearchReport.objects.select_related("security", "brokerage")
        .filter(source="naver", report_date__gte=window_start)
        .exclude(target_price__isnull=True)
        .exclude(previous_target_price__isnull=True)
    )

    if rule.watchlist_only:
        watchlist_ids = WatchlistEntry.objects.filter(enabled=True).values_list(
            "security_id",
            flat=True,
        )
        reports = reports.filter(security_id__in=watchlist_ids)

    grouped: dict[tuple[int, str], list[ResearchReport]] = {}
    for report in reports:
        ratio = report.revision_ratio
        if ratio is None or ratio == 0:
            continue
        direction = _direction_from_ratio(ratio)
        if direction is None or not _rule_matches_direction(rule, direction):
            continue
        if abs(ratio) < rule.min_revision_ratio:
            continue
        grouped.setdefault((report.security_id, direction), []).append(report)

    signals: list[RevisionSignal] = []
    for (security_id, direction), matched_reports in grouped.items():
        brokerages = {report.brokerage_id for report in matched_reports}
        revision_count = len(matched_reports)
        distinct_brokerage_count = len(brokerages)
        count_for_threshold = distinct_brokerage_count if rule.distinct_brokerage_only else revision_count
        ratios = [abs(report.revision_ratio) for report in matched_reports if report.revision_ratio is not None]
        average_revision_ratio = (
            sum(ratios, start=Decimal("0")) / len(ratios) if ratios else None
        )
        max_revision_ratio = max(ratios) if ratios else None
        immediate_hit = bool(
            max_revision_ratio and max_revision_ratio >= rule.immediate_revision_ratio
        )
        if count_for_threshold < rule.min_revision_count and not immediate_hit:
            continue

        security = matched_reports[0].security
        report_ids = sorted(report.id for report in matched_reports)
        dedupe_key = hashlib.sha1(
            f"{rule.id}:{security_id}:{direction}:{report_ids}".encode("utf-8")
        ).hexdigest()
        summary = _build_summary(
            security=security,
            direction=direction,
            revision_count=revision_count,
            distinct_brokerage_count=distinct_brokerage_count,
            average_revision_ratio=average_revision_ratio,
            max_revision_ratio=max_revision_ratio,
            reports=matched_reports,
        )
        signals.append(
            RevisionSignal(
                security=security,
                direction=direction,
                reports=matched_reports,
                revision_count=revision_count,
                distinct_brokerage_count=distinct_brokerage_count,
                average_revision_ratio=average_revision_ratio,
                max_revision_ratio=max_revision_ratio,
                dedupe_key=dedupe_key,
                summary=summary,
                raw_payload={
                    "report_ids": report_ids,
                    "brokerages": [report.brokerage.name for report in matched_reports],
                    "ratios": [str(report.revision_ratio) for report in matched_reports],
                },
            )
        )

    return signals


def _direction_from_ratio(ratio: Decimal) -> str | None:
    if ratio > 0:
        return AlertRule.DIRECTION_UP
    if ratio < 0:
        return AlertRule.DIRECTION_DOWN
    return None


def _rule_matches_direction(rule: AlertRule, direction: str) -> bool:
    return rule.direction == AlertRule.DIRECTION_BOTH or rule.direction == direction


def _format_eps(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{Decimal(value):,.2f}"
    except Exception:  # noqa: BLE001
        return str(value)


def _build_summary(
    security: Security,
    direction: str,
    revision_count: int,
    distinct_brokerage_count: int,
    average_revision_ratio: Decimal | None,
    max_revision_ratio: Decimal | None,
    reports: list[ResearchReport],
) -> str:
    direction_text = "상향" if direction == AlertRule.DIRECTION_UP else "하향"
    direction_emoji = "📈" if direction == AlertRule.DIRECTION_UP else "📉"
    latest_eps = None
    report_lines = []
    for report in sorted(reports, key=lambda item: item.report_date, reverse=True):
        if latest_eps is None and report.eps_forecast is not None:
            latest_eps = report.eps_forecast
        report_lines.append(
            (
                f"📝 {report.report_date:%Y-%m-%d} | {report.brokerage.name} | "
                f"{report.previous_target_price:,} -> {report.target_price:,}원 | "
                f"{report.revision_ratio}% | EPS {_format_eps(report.eps_forecast)}"
            )
        )

    avg_text = f"{average_revision_ratio}%" if average_revision_ratio is not None else "-"
    max_text = f"{max_revision_ratio}%" if max_revision_ratio is not None else "-"
    body = "\n".join(report_lines)
    return (
        f"🏢 {security.name} ({security.symbol})\n"
        f"{direction_emoji} 방향: {direction_text} 리비전\n"
        f"🏦 증권사 수: {distinct_brokerage_count} | 리포트 수: {revision_count}\n"
        f"📊 평균 변동률: {avg_text} | 최대 변동률: {max_text}\n"
        f"🧮 EPS(최신): {_format_eps(latest_eps)}\n"
        f"{body}"
    )
