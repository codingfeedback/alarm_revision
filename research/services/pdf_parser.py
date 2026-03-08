from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader


def extract_pdf_text(session, pdf_url: str, timeout: int, max_pages: int = 3) -> str:
    response = session.get(pdf_url, timeout=timeout)
    response.raise_for_status()
    reader = PdfReader(BytesIO(response.content))
    texts: list[str] = []
    for page in reader.pages[:max_pages]:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


def extract_target_price_from_pdf(text: str) -> int | None:
    patterns = [
        r"목표주가\s*[:：]?\s*([0-9,]+)",
        r"목표 가격\s*[:：]?\s*([0-9,]+)",
        r"TP\s*[:：]?\s*([0-9,]+)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, text, flags=re.IGNORECASE)
        if matched:
            return int(matched.group(1).replace(",", ""))
    return None


def extract_eps_forecast_from_pdf(text: str) -> str | None:
    patterns = [
        r"EPS\s*[:：]?\s*([0-9,]+(?:\.[0-9]+)?)",
        r"EPS\(원\)\s*[:：]?\s*([0-9,]+(?:\.[0-9]+)?)",
        r"지배주주EPS\s*[:：]?\s*([0-9,]+(?:\.[0-9]+)?)",
        r"2026E\s+EPS\s*([0-9,]+(?:\.[0-9]+)?)",
        r"2025E\s+EPS\s*([0-9,]+(?:\.[0-9]+)?)",
        r"2026E\s+지배주주EPS\s*([0-9,]+(?:\.[0-9]+)?)",
        r"2025E\s+지배주주EPS\s*([0-9,]+(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, text, flags=re.IGNORECASE)
        if matched:
            return matched.group(1).replace(",", "")
    return None
