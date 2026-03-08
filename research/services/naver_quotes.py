from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from django.conf import settings


@dataclass(slots=True)
class StockPriceSnapshot:
    symbol: str
    current_price: int | None = None
    previous_close: int | None = None


class NaverQuoteCollector:
    quote_url = "https://finance.naver.com/item/main.naver"

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.RESEARCH_REQUEST_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                )
            }
        )

    def fetch_snapshot(self, symbol: str) -> StockPriceSnapshot:
        response = self.session.get(
            self.quote_url,
            params={"code": symbol},
            timeout=self.timeout,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return self.parse_snapshot(symbol=symbol, html=response.text)

    def fetch_snapshots(self, symbols: list[str]) -> dict[str, StockPriceSnapshot]:
        snapshots: dict[str, StockPriceSnapshot] = {}
        for symbol in symbols:
            try:
                snapshots[symbol] = self.fetch_snapshot(symbol)
            except Exception:  # noqa: BLE001
                snapshots[symbol] = StockPriceSnapshot(symbol=symbol)
        return snapshots

    @staticmethod
    def parse_snapshot(symbol: str, html: str) -> StockPriceSnapshot:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        current_price = _extract_price(text, r"현재가\s*([0-9,]+)")
        previous_close = _extract_price(text, r"전일가\s*([0-9,]+)")
        return StockPriceSnapshot(
            symbol=symbol,
            current_price=current_price,
            previous_close=previous_close,
        )


def _extract_price(text: str, pattern: str) -> int | None:
    matched = re.search(pattern, text)
    if not matched:
        return None
    try:
        return int(matched.group(1).replace(",", ""))
    except ValueError:
        return None
