from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from alerts.services.digests import build_digest_message, matches_us_dst_mode
from alerts.services.orchestrator import ensure_default_rule, run_alert_cycle
from alerts.services.revision_detector import detect_signals
from alerts.services.telegram import TelegramNotifier
from research.services.fmp import FMPResearchCollector
from research.services.ingestion import ingest_reports
from research.services.naver import NaverResearchCollector
from research.services.naver_quotes import NaverQuoteCollector


class Command(BaseCommand):
    help = "Send a scheduled digest message for domestic or overseas revisions."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--region", choices=["domestic", "overseas"], required=True)
        parser.add_argument("--pages", type=int, default=3)
        parser.add_argument(
            "--respect-us-dst",
            choices=["any", "dst", "standard"],
            default="any",
        )
        parser.add_argument("--skip-live-alerts", action="store_true")

    def handle(self, *args, **options):
        rule = ensure_default_rule()
        notifier = TelegramNotifier()
        region = options["region"]
        summary: dict[str, object] = {
            "region": region,
            "reports_seen": 0,
            "reports_created": 0,
            "reports_updated": 0,
            "alert_events_created": 0,
            "alert_events_sent": 0,
            "alert_events_suppressed": 0,
            "digest_sent": False,
            "signal_count": 0,
            "skipped": False,
            "skip_reason": "",
        }

        if region == "domestic":
            collector = NaverResearchCollector()
            reports = []
            for page in range(1, options["pages"] + 1):
                reports.extend(collector.parse_listing(collector.fetch_listing_html(page=page)))
            created, updated = ingest_reports(reports)
            summary.update(
                {
                    "reports_seen": len(reports),
                    "reports_created": created,
                    "reports_updated": updated,
                }
            )
            if not options["skip_live_alerts"]:
                alert_result = run_alert_cycle(
                    sources=["naver"],
                    rule_names=[rule.name],
                )
                summary["alert_events_created"] = alert_result["created_events"]
                summary["alert_events_sent"] = alert_result["sent_events"]
                summary["alert_events_suppressed"] = alert_result["suppressed_events"]

            signals = detect_signals(rule, sources=["naver"])
            summary["signal_count"] = len(signals)
            quote_collector = NaverQuoteCollector()
            price_snapshots = quote_collector.fetch_snapshots(
                [signal.security.symbol for signal in signals]
            )
            message = build_digest_message(
                region_label="국내",
                region_emoji="🇰🇷",
                rule=rule,
                signals=signals,
                note=(
                    f"수집 {len(reports)}건 | 신규 {created}건 | 갱신 {updated}건 | "
                    f"즉시알림 {summary['alert_events_sent']}건 | "
                    f"중복억제 {summary['alert_events_suppressed']}건"
                ),
                price_snapshots=price_snapshots,
            )
        else:
            mode = options["respect_us_dst"]
            if not matches_us_dst_mode(mode):
                summary["skipped"] = True
                summary["skip_reason"] = "dst_mode_mismatch"
                self.stdout.write(self.style.WARNING(json.dumps(summary, ensure_ascii=False)))
                return

            collector = FMPResearchCollector()
            if not collector.is_configured():
                summary["skip_reason"] = "missing_fmp_config"
                message = build_digest_message(
                    region_label="해외",
                    region_emoji="🌎",
                    rule=rule,
                    signals=[],
                    unavailable_reason="해외 API 키가 없어 해외 리비전 데이터를 가져오지 못했습니다.",
                )
            else:
                reports = collector.fetch_reports()
                created, updated = ingest_reports(reports)
                summary.update(
                    {
                        "reports_seen": len(reports),
                        "reports_created": created,
                        "reports_updated": updated,
                    }
                )
                if not options["skip_live_alerts"]:
                    alert_result = run_alert_cycle(
                        sources=["fmp"],
                        rule_names=[rule.name],
                    )
                    summary["alert_events_created"] = alert_result["created_events"]
                    summary["alert_events_sent"] = alert_result["sent_events"]
                    summary["alert_events_suppressed"] = alert_result["suppressed_events"]

                signals = detect_signals(rule, sources=["fmp"])
                summary["signal_count"] = len(signals)
                message = build_digest_message(
                    region_label="해외",
                    region_emoji="🌎",
                    rule=rule,
                    signals=signals,
                    note=(
                        f"수집 {len(reports)}건 | 신규 {created}건 | 갱신 {updated}건 | "
                        f"즉시알림 {summary['alert_events_sent']}건 | "
                        f"중복억제 {summary['alert_events_suppressed']}건"
                    ),
                )

        if notifier.is_configured():
            notifier.send_message(message)
            summary["digest_sent"] = True

        self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False)))
