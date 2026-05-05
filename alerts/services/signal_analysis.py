from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

from alerts.models import AlertEvent
from research.models import ResearchReport

if TYPE_CHECKING:
    from alerts.services.revision_detector import RevisionSignal


MIN_TARGET_TO_PRICE = Decimal("0.30")
MAX_TARGET_TO_PRICE = Decimal("5.00")


@dataclass(slots=True)
class SignalAnalysis:
    alert_type_label: str
    alert_type_comment: str
    signal_check_label: str
    signal_check_comment: str
    reliability_label: str
    reliability_comment: str
    target_price: int | None
    upside_ratio: Decimal | None
    eps_line: str
    price_reaction_line: str


def analyze_signal(
    signal: RevisionSignal,
    *,
    current_price: int | None = None,
    previous_close: int | None = None,
) -> SignalAnalysis:
    latest_report = signal.reports[0]
    target_price = latest_report.target_price
    upside_ratio = _compute_upside_ratio(
        current_price=current_price,
        target_price=target_price,
    )
    signal_check_label, signal_check_comment = _build_signal_check(
        current_price=current_price,
        target_price=target_price,
        upside_ratio=upside_ratio,
    )
    eps_line, eps_direction = _build_eps_line(latest_report)
    price_reaction_line = _build_price_reaction_line(
        current_price=current_price,
        previous_close=previous_close,
    )
    reliability_label, reliability_comment = _build_reliability(
        signal=signal,
        signal_check_label=signal_check_label,
        eps_direction=eps_direction,
        upside_ratio=upside_ratio,
    )
    alert_type_label, alert_type_comment = _build_alert_type(signal)

    return SignalAnalysis(
        alert_type_label=alert_type_label,
        alert_type_comment=alert_type_comment,
        signal_check_label=signal_check_label,
        signal_check_comment=signal_check_comment,
        reliability_label=reliability_label,
        reliability_comment=reliability_comment,
        target_price=target_price,
        upside_ratio=upside_ratio,
        eps_line=eps_line,
        price_reaction_line=price_reaction_line,
    )


def _compute_upside_ratio(
    *,
    current_price: int | None,
    target_price: int | None,
) -> Decimal | None:
    if current_price is None or target_price is None or current_price == 0:
        return None
    return (
        (Decimal(target_price) - Decimal(current_price))
        / Decimal(current_price)
        * Decimal("100")
    ).quantize(Decimal("0.01"))


def _build_signal_check(
    *,
    current_price: int | None,
    target_price: int | None,
    upside_ratio: Decimal | None,
) -> tuple[str, str]:
    if current_price is None or target_price is None:
        return "확인 제한", "현재가 또는 목표가가 없어 목표가 괴리 기반 점검은 생략했습니다."

    target_to_price = Decimal(target_price) / Decimal(current_price)
    if target_to_price < MIN_TARGET_TO_PRICE:
        return (
            "검토 필요",
            f"최신 목표가가 현재가의 {target_to_price:.2f}배로 낮아 PDF 파싱 오류 가능성을 확인해야 합니다.",
        )
    if target_to_price > MAX_TARGET_TO_PRICE:
        return (
            "검토 필요",
            f"최신 목표가가 현재가의 {target_to_price:.2f}배로 높아 PDF 파싱 오류 가능성을 확인해야 합니다.",
        )
    if upside_ratio is None:
        return "확인 제한", "목표가 괴리를 계산하지 못했습니다."
    return "정상", "목표가와 현재가 괴리가 비정상 범위를 벗어나지 않았습니다."


def _build_eps_line(latest_report: ResearchReport) -> tuple[str, str]:
    current_eps = latest_report.eps_forecast
    if current_eps is None:
        return "EPS: N/A", "unknown"

    previous_report = (
        ResearchReport.objects.filter(
            security=latest_report.security,
            brokerage=latest_report.brokerage,
            report_date__lt=latest_report.report_date,
        )
        .exclude(eps_forecast__isnull=True)
        .order_by("-report_date", "-created_at")
        .first()
    )
    if previous_report is None or previous_report.eps_forecast is None:
        return f"EPS: {_format_decimal(current_eps)}", "unknown"

    previous_eps = Decimal(previous_report.eps_forecast)
    current_eps_decimal = Decimal(current_eps)
    if previous_eps == 0:
        return f"EPS: {_format_decimal(current_eps)}", "unknown"

    ratio = ((current_eps_decimal - previous_eps) / previous_eps * Decimal("100")).quantize(
        Decimal("0.01")
    )
    direction = "up" if ratio > 0 else "down" if ratio < 0 else "flat"
    return (
        f"EPS: {_format_decimal(previous_eps)} -> {_format_decimal(current_eps_decimal)} ({ratio:+.2f}%)",
        direction,
    )


def _build_price_reaction_line(
    *,
    current_price: int | None,
    previous_close: int | None,
) -> str:
    if current_price is None or previous_close is None or previous_close == 0:
        return "최근 주가 반응: N/A"
    ratio = (
        (Decimal(current_price) - Decimal(previous_close))
        / Decimal(previous_close)
        * Decimal("100")
    ).quantize(Decimal("0.01"))
    return f"최근 주가 반응: 전일 대비 {ratio:+.2f}%"


def _build_reliability(
    *,
    signal: RevisionSignal,
    signal_check_label: str,
    eps_direction: str,
    upside_ratio: Decimal | None,
) -> tuple[str, str]:
    if signal_check_label == "검토 필요":
        return "낮음", "목표가 숫자 점검에서 이상 가능성이 있어 원문 확인이 필요합니다."

    score = 0
    if signal.distinct_brokerage_count >= 3:
        score += 2
    elif signal.distinct_brokerage_count >= 2:
        score += 1
    if signal.max_revision_ratio and signal.max_revision_ratio >= Decimal("15"):
        score += 1
    if eps_direction == "up":
        score += 2
    elif eps_direction == "down":
        score -= 1
    if upside_ratio is not None and Decimal("10") <= upside_ratio <= Decimal("80"):
        score += 1

    if score >= 5:
        return "높음", "여러 증권사의 같은 방향 조정과 실적/괴리 조건이 함께 확인됐습니다."
    if score >= 2:
        return "보통", "리비전 방향은 확인되지만 EPS 또는 가격 반영 여부는 추가 확인이 좋습니다."
    return "낮음", "조건 일부만 확인되어 원문과 후속 리포트를 함께 보는 편이 좋습니다."


def _build_alert_type(signal: RevisionSignal) -> tuple[str, str]:
    previous_event = (
        AlertEvent.objects.filter(
            security=signal.security,
            direction=signal.direction,
            triggered_at__gte=timezone.now() - timedelta(days=14),
        )
        .order_by("-triggered_at")
        .first()
    )
    if previous_event is None:
        return "신규 리비전", "최근 같은 방향으로 저장된 알림 이력이 없습니다."
    if signal.distinct_brokerage_count > previous_event.distinct_brokerage_count:
        return (
            "기존 신호 강화",
            f"증권사 수가 {previous_event.distinct_brokerage_count}곳에서 {signal.distinct_brokerage_count}곳으로 늘었습니다.",
        )
    return "기존 신호 유지", "같은 방향의 리비전 신호가 최근에도 확인됐습니다."


def _format_decimal(value: Decimal) -> str:
    return f"{Decimal(value):,.2f}"
