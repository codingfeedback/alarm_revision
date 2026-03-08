from __future__ import annotations

import re
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone

from alerts.models import AlertRule
from alerts.services.revision_detector import RevisionSignal

US_EASTERN_TZ = ZoneInfo("America/New_York")


def is_us_dst_active(now: datetime | None = None) -> bool:
    current = now or timezone.now()
    eastern = current.astimezone(US_EASTERN_TZ)
    return bool(eastern.dst())


def matches_us_dst_mode(mode: str, now: datetime | None = None) -> bool:
    if mode == "any":
        return True
    active = is_us_dst_active(now=now)
    return (mode == "dst" and active) or (mode == "standard" and not active)


def build_digest_message(
    *,
    region_label: str,
    region_emoji: str,
    rule: AlertRule,
    signals: list[RevisionSignal],
    now: datetime | None = None,
    note: str = "",
    unavailable_reason: str = "",
) -> str:
    generated_at = now or timezone.localtime()
    lines = [
        f"{region_emoji} {region_label} 정기 점검 | {generated_at:%Y-%m-%d %H:%M}",
        (
            f"📌 기준: 최근 {rule.lookback_days}일, 서로 다른 증권사 "
            f"{rule.min_revision_count}곳 이상 목표가 리비전"
        ),
    ]
    if note:
        lines.append(f"ℹ️ 상태: {note}")
    if unavailable_reason:
        lines.append(f"⚠️ 안내: {unavailable_reason}")
        return "\n".join(lines)
    if not signals:
        lines.append("🔕 현재 기준 리비전 없음")
        return "\n".join(lines)

    lines.append(f"✅ 감지 종목: {len(signals)}건")
    for signal in _sorted_signals(signals):
        latest_report = signal.reports[0]
        ratio = signal.average_revision_ratio or signal.max_revision_ratio
        ratio_text = f"{ratio:+.2f}%" if ratio is not None else "N/A"
        eps_value = next(
            (report.eps_forecast for report in signal.reports if report.eps_forecast is not None),
            None,
        )
        eps_text = f"{eps_value:,.2f}" if eps_value is not None else "N/A"
        lines.append(
            (
                f"{'📈' if signal.direction == AlertRule.DIRECTION_UP else '📉'} "
                f"{signal.security.name} ({signal.security.symbol}) | 증권사 {signal.distinct_brokerage_count}곳 "
                f"| 평균 {ratio_text} | EPS {eps_text}"
            )
        )
        insight = _insight_from_report(latest_report.title, latest_report.summary)
        if insight:
            lines.append(f"🧾 {insight}")
    return "\n".join(lines)


def _insight_from_report(title: str, summary: str) -> str:
    summary_line = _first_sentence(summary)
    title_line = _normalize_text(title)
    if summary_line and summary_line != title_line:
        return summary_line
    return title_line[:80]


def _first_sentence(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    parts = re.split(r"(?<=[.!?다])\s+", normalized)
    return parts[0][:80].strip()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _sorted_signals(signals: list[RevisionSignal]) -> list[RevisionSignal]:
    return sorted(
        signals,
        key=lambda item: (
            item.distinct_brokerage_count,
            item.max_revision_ratio or 0,
            item.security.symbol,
        ),
        reverse=True,
    )
