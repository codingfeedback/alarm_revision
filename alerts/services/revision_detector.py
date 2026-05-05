from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from alerts.models import AlertRule
from alerts.services.opinion_engine import assess_signal
from research.models import ResearchReport, Security, WatchlistEntry
from research.services.naver_quotes import StockPriceSnapshot

STOCK_SPLIT_KEYWORDS = (
    "액면분할",
    "주식분할",
    "분할 반영",
    "분할후",
    "분할 후",
    "stock split",
    "split-adjusted",
    "split adjusted",
)
STOCK_SPLIT_RATIOS = (
    Decimal("0.50"),
    Decimal("0.20"),
    Decimal("0.10"),
    Decimal("0.05"),
    Decimal("0.02"),
    Decimal("0.01"),
)
STOCK_SPLIT_RATIO_TOLERANCE = Decimal("0.03")


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


def attach_current_prices(
    signals: list[RevisionSignal],
    snapshots: dict[str, StockPriceSnapshot],
) -> list[RevisionSignal]:
    for signal in signals:
        snapshot = snapshots.get(signal.security.symbol)
        current_price = snapshot.current_price if snapshot is not None else None
        signal.summary = _build_summary(
            security=signal.security,
            direction=signal.direction,
            revision_count=signal.revision_count,
            distinct_brokerage_count=signal.distinct_brokerage_count,
            average_revision_ratio=signal.average_revision_ratio,
            max_revision_ratio=signal.max_revision_ratio,
            reports=signal.reports,
            current_price=current_price,
        )
        if current_price is not None:
            signal.raw_payload["current_price"] = current_price
    return signals


def detect_signals(
    rule: AlertRule,
    sources: list[str] | None = None,
    market: str | None = None,
) -> list[RevisionSignal]:
    window_start = timezone.localdate() - timedelta(days=rule.lookback_days)
    reports = (
        ResearchReport.objects.select_related("security", "brokerage")
        .filter(report_date__gte=window_start)
        .exclude(target_price__isnull=True)
        .exclude(previous_target_price__isnull=True)
    )

    if sources:
        reports = reports.filter(source__in=sources)
    if market:
        reports = reports.filter(security__market__iexact=market)
    if rule.watchlist_only:
        watchlist_ids = WatchlistEntry.objects.filter(enabled=True).values_list(
            "security_id",
            flat=True,
        )
        reports = reports.filter(security_id__in=watchlist_ids)

    grouped: dict[tuple[int, str], list[ResearchReport]] = {}
    for report in reports:
        if is_stock_split_adjustment(report):
            continue
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
        count_for_threshold = (
            distinct_brokerage_count if rule.distinct_brokerage_only else revision_count
        )
        ratios = [
            abs(report.revision_ratio)
            for report in matched_reports
            if report.revision_ratio is not None
        ]
        average_revision_ratio = (
            sum(ratios, start=Decimal("0")) / len(ratios) if ratios else None
        )
        max_revision_ratio = max(ratios) if ratios else None
        immediate_hit = bool(
            max_revision_ratio and max_revision_ratio >= rule.immediate_revision_ratio
        )
        if count_for_threshold < rule.min_revision_count and not immediate_hit:
            continue

        matched_reports = sorted(
            matched_reports,
            key=lambda item: (item.report_date, item.created_at),
            reverse=True,
        )
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
                    "sources": sorted({report.source for report in matched_reports}),
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


def is_stock_split_adjustment(report: ResearchReport) -> bool:
    if not report.target_price or not report.previous_target_price:
        return False
    if report.target_price >= report.previous_target_price:
        return False

    text = _split_detection_text(report)
    if any(keyword in text for keyword in STOCK_SPLIT_KEYWORDS):
        return True

    target_to_previous = (
        Decimal(report.target_price) / Decimal(report.previous_target_price)
    ).quantize(Decimal("0.0001"))
    return any(
        abs(target_to_previous - split_ratio) <= STOCK_SPLIT_RATIO_TOLERANCE
        for split_ratio in STOCK_SPLIT_RATIOS
    )


def _split_detection_text(report: ResearchReport) -> str:
    parts = [
        report.title,
        report.summary,
        _raw_payload_text(report.raw_payload),
    ]
    return " ".join(part for part in parts if part).lower()


def _raw_payload_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_raw_payload_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_raw_payload_text(item) for item in value)
    return str(value)


def _format_eps(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{Decimal(value):,.2f}"
    except Exception:  # noqa: BLE001
        return str(value)


def _format_ratio(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{Decimal(value):.2f}%"


def _first_sentence(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if not normalized:
        return ""
    parts = re.split(r"(?<=[.!?다])\s+", normalized)
    return parts[0][:80].strip()


def _build_insight(report: ResearchReport) -> str:
    summary = _first_sentence(report.summary)
    title = re.sub(r"\s+", " ", report.title).strip()
    if summary and summary != title:
        return summary
    return title[:80]


def _build_summary(
    security: Security,
    direction: str,
    revision_count: int,
    distinct_brokerage_count: int,
    average_revision_ratio: Decimal | None,
    max_revision_ratio: Decimal | None,
    reports: list[ResearchReport],
    current_price: int | None = None,
) -> str:
    direction_text = "상향" if direction == AlertRule.DIRECTION_UP else "하향"
    direction_emoji = "📈" if direction == AlertRule.DIRECTION_UP else "📉"
    latest_report = reports[0]
    latest_eps = next(
        (report.eps_forecast for report in reports if report.eps_forecast is not None),
        None,
    )
    insight = _build_insight(latest_report)
    signal = RevisionSignal(
        security=security,
        direction=direction,
        reports=reports,
        revision_count=revision_count,
        distinct_brokerage_count=distinct_brokerage_count,
        average_revision_ratio=average_revision_ratio,
        max_revision_ratio=max_revision_ratio,
        dedupe_key="",
        summary="",
        raw_payload={},
    )
    opinion = assess_signal(signal, current_price=current_price)

    report_lines = []
    for report in reports:
        report_lines.append(
            (
                f"📝 {report.report_date:%Y-%m-%d} | {report.brokerage.name}\n"
                f"목표가 {report.previous_target_price:,} -> {report.target_price:,}원\n"
                f"변동률 {_format_ratio(report.revision_ratio)} | EPS {_format_eps(report.eps_forecast)}"
            )
        )

    avg_text = _format_ratio(average_revision_ratio)
    max_text = _format_ratio(max_revision_ratio)
    lines = [
        f"🏢 {security.name} ({security.symbol})",
        f"{direction_emoji} 방향: {direction_text} 리비전",
        f"🏦 증권사 수: {distinct_brokerage_count} | 리포트 수: {revision_count}",
        f"📊 평균 변동률: {avg_text} | 최대 변동률: {max_text}",
    ]
    if insight:
        lines.append(f"🧾 요약: {insight}")
    if current_price is not None:
        lines.append(f"💰 현재가: {current_price:,}원")
    lines.append(f"🧪 EPS(최신): {_format_eps(latest_eps)}")
    lines.append(f"🤖 참고 의견: {opinion.label}")
    lines.append(f"💬 {opinion.comment}")
    lines.extend(report_lines)
    return "\n".join(lines)
