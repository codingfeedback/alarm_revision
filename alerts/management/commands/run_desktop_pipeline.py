from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from alerts.services.orchestrator import run_alert_cycle
from research.services.csv_importer import load_reports_from_csv
from research.services.ingestion import ingest_reports
from research.services.naver import NaverResearchCollector


class Command(BaseCommand):
    help = "Run the desktop ingestion and alert pipeline in one command."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--source", choices=["naver", "csv", "none"], default="naver")
        parser.add_argument("--csv-path", type=str)
        parser.add_argument("--pages", type=int, default=1)
        parser.add_argument("--save-html", action="store_true")
        parser.add_argument("--skip-alerts", action="store_true")
        parser.add_argument("--summary-json", type=str)

    def handle(self, *args, **options):
        summary = {
            "source": options["source"],
            "reports_seen": 0,
            "reports_created": 0,
            "reports_updated": 0,
            "alert_events_created": 0,
            "alert_events_sent": 0,
        }

        if options["source"] == "naver":
            collector = NaverResearchCollector()
            reports = []
            for page in range(1, options["pages"] + 1):
                html = collector.fetch_listing_html(page=page)
                if options["save_html"]:
                    snapshot_path = collector.save_snapshot(html, page)
                    self.stdout.write(f"saved snapshot: {snapshot_path}")
                reports.extend(collector.parse_listing(html))
            summary["reports_seen"] = len(reports)
            created, updated = ingest_reports(reports)
            summary["reports_created"] = created
            summary["reports_updated"] = updated
        elif options["source"] == "csv":
            csv_path = options.get("csv_path")
            if not csv_path:
                raise CommandError("--csv-path is required when --source csv")
            reports = load_reports_from_csv(Path(csv_path).resolve())
            summary["reports_seen"] = len(reports)
            created, updated = ingest_reports(reports)
            summary["reports_created"] = created
            summary["reports_updated"] = updated

        if not options["skip_alerts"]:
            alert_result = run_alert_cycle()
            summary["alert_events_created"] = alert_result["created_events"]
            summary["alert_events_sent"] = alert_result["sent_events"]

        if options.get("summary_json"):
            summary_path = Path(options["summary_json"]).resolve()
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(f"summary written: {summary_path}")

        self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False)))
