from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from alerts.services.orchestrator import (
    ensure_default_rule,
    ensure_observation_rule,
    run_alert_cycle,
)
from research.services.fmp import FMPResearchCollector
from research.services.ingestion import ingest_reports
from research.services.naver import NaverResearchCollector


class Command(BaseCommand):
    help = "Poll domestic and overseas sources and send only immediate revision alerts."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--naver-pages", type=int, default=1)
        parser.add_argument("--skip-overseas", action="store_true")

    def handle(self, *args, **options):
        now = timezone.localtime()
        confirmed_rule = ensure_default_rule()
        observation_rule = ensure_observation_rule()
        summary = {
            "domestic_reports_seen": 0,
            "domestic_reports_created": 0,
            "domestic_reports_updated": 0,
            "domestic_alert_events_created": 0,
            "domestic_alert_events_sent": 0,
            "domestic_observation_events_created": 0,
            "domestic_observation_events_sent": 0,
            "overseas_reports_seen": 0,
            "overseas_reports_created": 0,
            "overseas_reports_updated": 0,
            "overseas_alert_events_created": 0,
            "overseas_alert_events_sent": 0,
            "skipped": False,
        }

        if now.weekday() >= 5:
            summary["skipped"] = True
            self.stdout.write(self.style.WARNING(json.dumps(summary, ensure_ascii=False)))
            return

        collector = NaverResearchCollector()
        reports = []
        for page in range(1, options["naver_pages"] + 1):
            reports.extend(collector.parse_listing(collector.fetch_listing_html(page=page)))
        created, updated = ingest_reports(reports)
        observation_result = run_alert_cycle(
            sources=["naver"],
            rule_names=[observation_rule.name],
            max_distinct_brokerage_count=confirmed_rule.min_revision_count - 1,
            message_prefix="⚡ 선행 관찰 알림\n- 확정 신호 아님\n- 서로 다른 증권사 2곳 조건 전, 큰 폭 리비전 1차 감지",
        )
        alert_result = run_alert_cycle(
            sources=["naver"],
            rule_names=[confirmed_rule.name],
        )
        summary.update(
            {
                "domestic_reports_seen": len(reports),
                "domestic_reports_created": created,
                "domestic_reports_updated": updated,
                "domestic_alert_events_created": alert_result["created_events"],
                "domestic_alert_events_sent": alert_result["sent_events"],
                "domestic_alert_events_suppressed": alert_result["suppressed_events"],
                "domestic_observation_events_created": observation_result["created_events"],
                "domestic_observation_events_sent": observation_result["sent_events"],
                "domestic_observation_events_suppressed": observation_result[
                    "suppressed_events"
                ],
            }
        )

        if not options["skip_overseas"]:
            overseas_collector = FMPResearchCollector()
            if overseas_collector.is_configured():
                overseas_reports = overseas_collector.fetch_reports()
                created, updated = ingest_reports(overseas_reports)
                alert_result = run_alert_cycle(
                    sources=["fmp"],
                    rule_names=[confirmed_rule.name],
                )
                summary.update(
                    {
                        "overseas_reports_seen": len(overseas_reports),
                        "overseas_reports_created": created,
                        "overseas_reports_updated": updated,
                        "overseas_alert_events_created": alert_result["created_events"],
                        "overseas_alert_events_sent": alert_result["sent_events"],
                        "overseas_alert_events_suppressed": alert_result[
                            "suppressed_events"
                        ],
                    }
                )

        self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False)))
