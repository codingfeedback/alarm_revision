from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from alerts.models import AlertRule

if TYPE_CHECKING:
    from alerts.services.revision_detector import RevisionSignal


@dataclass(slots=True)
class OpinionAssessment:
    label: str
    comment: str
    source_opinion: str
    upside_ratio: Decimal | None


def assess_signal(
    signal: RevisionSignal,
    *,
    current_price: int | None = None,
) -> OpinionAssessment:
    latest_report = signal.reports[0]
    source_opinion = _normalize_source_opinion(
        next((report.opinion for report in signal.reports if report.opinion), "")
    )
    latest_target_price = latest_report.target_price
    upside_ratio = _compute_upside_ratio(
        current_price=current_price,
        target_price=latest_target_price,
    )

    direction_sign = 1 if signal.direction == AlertRule.DIRECTION_UP else -1
    score = direction_sign

    if signal.distinct_brokerage_count >= 3:
        score += direction_sign
    if signal.distinct_brokerage_count >= 5:
        score += direction_sign

    revision_ratio = signal.max_revision_ratio or signal.average_revision_ratio
    if revision_ratio is not None:
        revision_strength = abs(Decimal(revision_ratio))
        if revision_strength >= Decimal("30"):
            score += direction_sign * 2
        elif revision_strength >= Decimal("15"):
            score += direction_sign

    score += _opinion_score(source_opinion)

    if upside_ratio is not None:
        if upside_ratio >= Decimal("40"):
            score += 2
        elif upside_ratio >= Decimal("20"):
            score += 1
        elif upside_ratio <= Decimal("-20"):
            score -= 2
        elif upside_ratio <= Decimal("0"):
            score -= 1

    label = _label_from_score(score)
    comment = _build_comment(
        label=label,
        signal=signal,
        upside_ratio=upside_ratio,
        source_opinion=source_opinion,
    )
    return OpinionAssessment(
        label=label,
        comment=comment,
        source_opinion=source_opinion,
        upside_ratio=upside_ratio,
    )


def _normalize_source_opinion(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""

    compact = re.sub(r"[\s/_-]+", "", text).lower()
    mappings = [
        ("적극매수", ("적극매수", "strongbuy", "convictionbuy")),
        ("적극매도", ("적극매도", "strongsell")),
        ("매수", ("매수", "buy", "outperform", "overweight", "accumulate", "tradingbuy")),
        ("중립", ("중립", "hold", "neutral", "marketperform", "equalweight")),
        ("매도", ("매도", "sell", "reduce", "underperform", "underweight")),
    ]
    for label, keywords in mappings:
        if any(keyword in compact for keyword in keywords):
            return label
    return text[:20]


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


def _opinion_score(source_opinion: str) -> int:
    return {
        "적극매수": 2,
        "매수": 1,
        "중립": 0,
        "매도": -1,
        "적극매도": -2,
    }.get(source_opinion, 0)


def _label_from_score(score: int) -> str:
    if score >= 6:
        return "적극매수"
    if score >= 3:
        return "매수"
    if score <= -6:
        return "적극매도"
    if score <= -3:
        return "매도"
    return "중립"


def _build_comment(
    *,
    label: str,
    signal: RevisionSignal,
    upside_ratio: Decimal | None,
    source_opinion: str,
) -> str:
    direction_text = "상향" if signal.direction == AlertRule.DIRECTION_UP else "하향"
    parts = [
        (
            f"최근 {signal.distinct_brokerage_count}개 증권사가 목표가를 {direction_text}했고 "
            f"리비전 강도는 평균 {_format_ratio(signal.average_revision_ratio)}입니다"
        )
    ]
    if upside_ratio is not None:
        if upside_ratio >= 0:
            parts.append(f"현재가 대비 최신 목표가 괴리는 {_format_ratio(upside_ratio)}로 상방 여지가 남아 있습니다")
        else:
            parts.append(f"현재가 대비 최신 목표가 괴리는 {_format_ratio(upside_ratio)}로 보수적 접근이 필요해 보입니다")
    if source_opinion:
        parts.append(f"최근 리포트 투자의견은 {source_opinion}입니다")
    elif label == "중립":
        parts.append("추가 확인 전에는 관망이 더 적절해 보입니다")
    return ". ".join(parts) + "."


def _format_ratio(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"{Decimal(value):+.2f}%"
