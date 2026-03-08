from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

from research.services.pdf_parser import (
    extract_eps_forecast_from_pdf,
    extract_pdf_text,
    extract_target_price_from_pdf,
)
from research.services.schemas import ParsedReport


class NaverResearchCollector:
    def __init__(self, source_url: str | None = None, timeout: int | None = None) -> None:
        self.source_url = source_url or settings.RESEARCH_SOURCE_URL
        self.timeout = timeout or settings.RESEARCH_REQUEST_TIMEOUT
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def fetch_listing_html(self, page: int = 1) -> str:
        response = self.session.get(
            self.source_url,
            params={"page": page},
            timeout=self.timeout,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def fetch_detail_html(self, detail_url: str) -> str:
        response = self.session.get(detail_url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def save_snapshot(self, html: str, page: int) -> None:
        snapshot_dir = settings.BASE_DIR / "data" / "raw" / "naver"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = snapshot_dir / f"listing_{timestamp}_p{page}.html"
        snapshot_path.write_text(html, encoding="utf-8")

    def parse_listing(self, html: str, fetch_details: bool = True) -> list[ParsedReport]:
        soup = BeautifulSoup(html, "lxml")
        reports: list[ParsedReport] = []

        for row in soup.select("table.type_1 tr"):
            stock_link = row.select_one("a.stock_item[href]")
            title_link = row.select_one("td:nth-of-type(2) a[href]")
            brokerage_cell = row.select_one("td:nth-of-type(3)")
            date_cell = row.select_one("td.date")
            if stock_link is None or title_link is None or brokerage_cell is None or date_cell is None:
                continue

            symbol = self._extract_symbol(stock_link.get("href", ""))
            if not symbol:
                continue

            security_name = stock_link.get_text(" ", strip=True)
            title = title_link.get_text(" ", strip=True)
            brokerage_name = brokerage_cell.get_text(" ", strip=True)
            report_date = self._parse_report_date(date_cell.get_text(" ", strip=True))
            detail_url = urljoin(self.source_url, title_link["href"])
            source_report_id = self._extract_nid(title_link["href"]) or self._build_source_report_id(
                title_link["href"],
                symbol,
                report_date,
            )

            report = ParsedReport(
                source="naver",
                source_report_id=source_report_id,
                symbol=symbol,
                security_name=security_name,
                brokerage_name=brokerage_name,
                title=title,
                report_date=report_date,
                report_url=detail_url,
                raw_payload={
                    "listing_href": title_link["href"],
                    "stock_href": stock_link.get("href", ""),
                },
            )

            if fetch_details:
                try:
                    detail_html = self.fetch_detail_html(detail_url)
                    report = self.parse_detail(report, detail_html)
                except requests.RequestException:
                    pass

            reports.append(report)

        return reports

    def parse_detail(self, report: ParsedReport, html: str) -> ParsedReport:
        soup = BeautifulSoup(html, "lxml")
        content_table = soup.select_one("table.type_1[summary*='본문']") or soup.select_one("table.type_1")
        if content_table is None:
            return report

        header = content_table.select_one("th.view_sbj")
        if header is not None:
            header_text = header.get_text(" ", strip=True)
            report.raw_payload["header_text"] = header_text
            if not report.report_date:
                report.report_date = self._parse_report_date(header_text)

        info = content_table.select_one("div.view_info_1")
        if info is not None:
            info_text = " ".join(info.get_text(" ", strip=True).split())
            report.target_price = self._extract_target_price(info_text)
            report.opinion = self._extract_opinion(info_text)
            report.raw_payload["info_text"] = info_text

        content = content_table.select_one("td.view_cnt div")
        if content is not None:
            report.summary = " ".join(content.get_text(" ", strip=True).split())

        pdf_link = content_table.select_one("th.view_report a[href]") or content_table.select_one("a.con_link[href]")
        if pdf_link is not None:
            pdf_url = pdf_link.get("href", "")
            report.raw_payload["pdf_url"] = pdf_url
            self._enrich_from_pdf(report, pdf_url)

        return report

    def _enrich_from_pdf(self, report: ParsedReport, pdf_url: str) -> None:
        if ".pdf" not in pdf_url.lower():
            return
        try:
            pdf_text = extract_pdf_text(self.session, pdf_url, timeout=self.timeout)
        except Exception:  # noqa: BLE001
            return

        compact_text = " ".join(pdf_text.split())
        if compact_text:
            report.raw_payload["pdf_excerpt"] = compact_text[:2000]

        if report.target_price is None:
            report.target_price = extract_target_price_from_pdf(compact_text)

        eps_value = extract_eps_forecast_from_pdf(compact_text)
        if eps_value:
            try:
                report.eps_forecast = Decimal(eps_value)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _extract_symbol(raw_href: str) -> str:
        query = parse_qs(urlparse(raw_href).query)
        code = query.get("code", [""])[0].strip()
        return code.replace("A", "")

    @staticmethod
    def _extract_nid(raw_href: str) -> str:
        query = parse_qs(urlparse(raw_href).query)
        return query.get("nid", [""])[0].strip()

    @staticmethod
    def _build_source_report_id(raw_href: str, symbol: str, report_date) -> str:
        href = raw_href.strip().replace("/", "_").replace("?", "_").replace("&", "_")
        date_text = report_date.isoformat() if report_date else "unknown-date"
        return f"{symbol}:{date_text}:{href}"[:120]

    @staticmethod
    def _parse_report_date(value: str):
        value = value.strip()
        matched = re.search(r"(\d{2,4})[.\-/](\d{2})[.\-/](\d{2})", value)
        if matched:
            year = int(matched.group(1))
            if year < 100:
                year += 2000
            month = int(matched.group(2))
            day = int(matched.group(3))
            return datetime(year, month, day).date()
        for fmt in ("%Y.%m.%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_target_price(text: str) -> int | None:
        matched = re.search(r"목표가\s*([0-9,]+)", text)
        if matched:
            return int(matched.group(1).replace(",", ""))
        matched = re.search(r"목표주가\s*([0-9,]+)", text)
        if matched:
            return int(matched.group(1).replace(",", ""))
        return None

    @staticmethod
    def _extract_opinion(text: str) -> str:
        matched = re.search(r"투자의견\s*([^|]+)", text)
        if matched:
            return matched.group(1).strip()
        return ""
