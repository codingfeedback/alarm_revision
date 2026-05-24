from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research.models import ResearchReport


STRONG_BUY_LABEL = "적극매수"


def build_signal_check_line(
    *,
    reliability_label: str,
    signal_check_label: str,
    with_colon: bool,
) -> str:
    if signal_check_label == "정상":
        return ""
    separator = ":" if with_colon else ""
    return (
        f"⚠️ 신호 확인{separator} "
        f"신뢰도 {reliability_label} | 점검 {signal_check_label}"
    )


def build_report_link_lines(
    *,
    reports: list[ResearchReport],
    opinion_label: str,
    max_links: int = 3,
) -> list[str]:
    if opinion_label != STRONG_BUY_LABEL:
        return []

    lines: list[str] = []
    seen_urls: set[str] = set()
    for report in reports:
        url = (report.report_url or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        lines.append(f"🔗 원문: {report.brokerage.name} {url}")
        if len(lines) >= max_links:
            break
    return lines
