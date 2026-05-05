from __future__ import annotations

from decimal import Decimal
from typing import Any


SPLIT_KEYWORDS = (
    "액면분할",
    "주식분할",
    "분할 반영",
    "분할후",
    "분할 후",
    "stock split",
    "split-adjusted",
    "split adjusted",
)
REVERSE_SPLIT_KEYWORDS = (
    "액면병합",
    "주식병합",
    "병합 반영",
    "reverse split",
)
CAPITAL_ACTION_KEYWORDS = (
    "무상증자",
    "유상증자",
    "권리락",
    "증자 반영",
    "신주 발행",
)
REORGANIZATION_KEYWORDS = (
    "인적분할",
    "물적분할",
    "기업분할",
    "분할합병",
    "합병",
    "지주회사 전환",
    "지주사 전환",
)
COVERAGE_RESET_KEYWORDS = (
    "커버리지 개시",
    "커버리지 재개",
    "신규 커버리지",
    "coverage initiation",
    "initiate coverage",
    "reinitiate coverage",
    "resuming coverage",
)
VALUATION_RESET_KEYWORDS = (
    "산정 기준 변경",
    "목표가 산정 기준 변경",
    "기준연도 변경",
)

DOWNWARD_SPLIT_RATIOS = (
    Decimal("0.50"),
    Decimal("0.20"),
    Decimal("0.10"),
    Decimal("0.05"),
    Decimal("0.02"),
    Decimal("0.01"),
)
RATIO_TOLERANCE = Decimal("0.03")


def should_skip_revision_report(report: Any) -> bool:
    text = report_text(report)
    if is_coverage_reset_text(text):
        return True
    return is_non_revision_price_adjustment(
        target_price=getattr(report, "target_price", None),
        previous_target_price=getattr(report, "previous_target_price", None),
        text=text,
    )


def should_skip_previous_target_link(item: Any) -> bool:
    return is_coverage_reset_text(report_text(item))


def is_stock_split_adjustment(report: Any) -> bool:
    return is_split_adjustment(
        target_price=getattr(report, "target_price", None),
        previous_target_price=getattr(report, "previous_target_price", None),
        text=report_text(report),
    )


def is_non_revision_price_adjustment(
    *,
    target_price: int | None,
    previous_target_price: int | None,
    text: str,
) -> bool:
    if not target_price or not previous_target_price:
        return False

    normalized = normalize_text(text)
    if has_any_keyword(normalized, CAPITAL_ACTION_KEYWORDS):
        return True
    if has_any_keyword(normalized, REORGANIZATION_KEYWORDS):
        return True
    if has_any_keyword(normalized, VALUATION_RESET_KEYWORDS):
        return True
    if is_split_adjustment(
        target_price=target_price,
        previous_target_price=previous_target_price,
        text=normalized,
    ):
        return True
    return is_reverse_split_adjustment(
        target_price=target_price,
        previous_target_price=previous_target_price,
        text=normalized,
    )


def is_split_adjustment(
    *,
    target_price: int | None,
    previous_target_price: int | None,
    text: str,
) -> bool:
    if not target_price or not previous_target_price:
        return False
    if target_price >= previous_target_price:
        return False

    normalized = normalize_text(text)
    if has_any_keyword(normalized, SPLIT_KEYWORDS):
        return True

    target_to_previous = (
        Decimal(target_price) / Decimal(previous_target_price)
    ).quantize(Decimal("0.0001"))
    return any(
        abs(target_to_previous - split_ratio) <= RATIO_TOLERANCE
        for split_ratio in DOWNWARD_SPLIT_RATIOS
    )


def is_reverse_split_adjustment(
    *,
    target_price: int | None,
    previous_target_price: int | None,
    text: str,
) -> bool:
    if not target_price or not previous_target_price:
        return False
    if target_price <= previous_target_price:
        return False
    return has_any_keyword(normalize_text(text), REVERSE_SPLIT_KEYWORDS)


def is_coverage_reset_text(text: str) -> bool:
    return has_any_keyword(normalize_text(text), COVERAGE_RESET_KEYWORDS)


def report_text(report: Any) -> str:
    parts = [
        getattr(report, "title", ""),
        getattr(report, "summary", ""),
        _raw_payload_text(getattr(report, "raw_payload", "")),
    ]
    return " ".join(part for part in parts if part)


def normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _raw_payload_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_raw_payload_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_raw_payload_text(item) for item in value)
    return str(value)
