from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from alerts.models import AlertRule
from alerts.services.opinion_engine import assess_signal
from alerts.services.revision_detector import RevisionSignal
from research.services.naver_quotes import StockPriceSnapshot

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
    price_snapshots: dict[str, StockPriceSnapshot] | None = None,
) -> str:
    generated_at = now or timezone.localtime()
    sections = [
        (
            f"{region_emoji} {region_label} 정기 점검 | {generated_at:%Y-%m-%d %H:%M}\n"
            f"📌 기준: 최근 {rule.lookback_days}일, 서로 다른 증권사 {rule.min_revision_count}곳 이상 목표가 리비전"
        )
    ]
    if note:
        sections.append(f"ℹ️ 상태\n{note}")
    if unavailable_reason:
        sections.append(f"⚠️ 안내\n{unavailable_reason}")
        return "\n\n".join(sections)
    if not signals:
        sections.append("🔕 결과\n현재 기준 리비전 없음")
        return "\n\n".join(sections)

    sections.append(f"✅ 감지 종목\n{len(signals)}건")
    for signal in _sorted_signals(signals):
        latest_report = signal.reports[0]
        ratio = signal.average_revision_ratio or signal.max_revision_ratio
        ratio_text = f"{ratio:+.2f}%" if ratio is not None else "N/A"
        eps_value = next(
            (report.eps_forecast for report in signal.reports if report.eps_forecast is not None),
            None,
        )
        eps_text = f"{eps_value:,.2f}" if eps_value is not None else "N/A"
        snapshot = (price_snapshots or {}).get(signal.security.symbol)
        current_price = snapshot.current_price if snapshot is not None else None
        opinion = assess_signal(signal, current_price=current_price)
        lines = [
            f"{'📈' if signal.direction == AlertRule.DIRECTION_UP else '📉'} {signal.security.name} ({signal.security.symbol})",
            f"증권사 {signal.distinct_brokerage_count}곳 | 평균 변동률 {ratio_text}",
        ]
        price_line = _build_price_line(
            snapshot=snapshot,
            target_price=latest_report.target_price,
        )
        if price_line:
            lines.append(price_line)
        lines.append(f"EPS {eps_text}")
        lines.append(f"🤖 참고 의견 {opinion.label}")
        lines.append(f"💬 {opinion.comment}")
        insight = _insight_from_report(latest_report.title, latest_report.summary)
        if insight:
            lines.append(f"요약: {insight}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _build_price_line(snapshot: StockPriceSnapshot | None, target_price: int | None) -> str:
    if snapshot is None or snapshot.current_price is None or target_price is None:
        return ""
    upside = (
        (Decimal(target_price) - Decimal(snapshot.current_price))
        / Decimal(snapshot.current_price)
        * Decimal("100")
    ).quantize(Decimal("0.01"))
    return f"현재가 {snapshot.current_price:,}원 | 최신TP {target_price:,}원 | 괴리 {upside:+.2f}%"


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
