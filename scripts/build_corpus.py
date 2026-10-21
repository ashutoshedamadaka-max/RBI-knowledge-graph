"""Build the corpus through the same monitoring path production uses (brief rule 6).

1. The hand-downloaded NBFC direction PDFs (data/source_pdfs), with status read from their
   live RBI page (Withdrawn watermark or not).
2. Predecessor circulars selected from RBI's register of withdrawn circulars by
   config/corpus/inclusion.yaml, fetched and checked by RegulatoryMonitor.
3. RBI's register applied, then successor linking, exactly as a scheduled run does.

Writes data/corpus/build-report.json. Use an isolated --data-dir, never the production one.
For PostgreSQL chunks, start scripts/dev_database.py and set VECTOR_BACKEND and DATABASE_URL.
"""
import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import clock  # noqa: E402
from app.config.settings import Settings  # noqa: E402
from app.ingestion.parser import parse_document  # noqa: E402
from app.ingestion.service import IngestionService  # noqa: E402
from app.models.monitoring import DiscoveredDocument, RegulatorySource, SourceType  # noqa: E402
from app.monitoring.fetcher import RbiHttpFetcher  # noqa: E402
from app.monitoring.linking import LinkingService  # noqa: E402
from app.monitoring.processor import MonitoringDocumentProcessor  # noqa: E402
from app.monitoring.service import RegulatoryMonitor  # noqa: E402
from app.monitoring.store import MonitoringStore  # noqa: E402
from app.monitoring.withdrawn_register import REGISTER_URL, apply_register, parse_register, select_predecessors  # noqa: E402

PAUSE_SECONDS = 1.5  # between requests to www.rbi.org.in


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--register-file", type=Path, help="Saved copy of the register page instead of fetching it.")
    args = parser.parse_args()
    settings = Settings(_env_file=None, data_dir=args.data_dir)
    ingestion = IngestionService(settings)
    processor = MonitoringDocumentProcessor(ingestion)
    fetcher = RbiHttpFetcher()
    monitor = RegulatoryMonitor(MonitoringStore(settings.runtime_dir / "monitoring.json"), fetcher, processor)
    failures: list[str] = []

    folder = ROOT / "data" / "source_pdfs"
    directions = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["directions"]
    for row in directions:
        path = folder / row["pdf_file_name"]
        if not path.exists():
            failures.append(f"missing PDF {row['pdf_file_name']}")
            continue
        content = path.read_bytes()
        found = DiscoveredDocument(canonical_url=row["page_url"], title=row["title"],
                                   metadata_hash=hashlib.sha256(content).hexdigest())
        try:
            ingestion.ingest_content(content, row["page_url"], row["pdf_file_name"], row["title"])
            text = "\n".join(parse_document(path, "application/pdf").pages)
            processor.assess_lifecycle(found, text, fetcher.lifecycle_resolution(found))
        except Exception as exc:  # report and continue; one bad file must not stop the build
            failures.append(f"{row['pdf_file_name']}: {exc}")
        time.sleep(PAUSE_SECONDS)
        print(f"direction {row['page_id']}", flush=True)

    page = (args.register_file.read_text(encoding="utf-8") if args.register_file
            else httpx.get(REGISTER_URL, follow_redirects=True, timeout=90).text)
    entries = parse_register(page)
    rule = yaml.safe_load((ROOT / "config" / "corpus" / "inclusion.yaml").read_text(encoding="utf-8"))["withdrawn_circulars"]
    decisions = select_predecessors(entries, rule)
    selected = {entry.page_url: entry for entry, included, _ in decisions if included}
    for number, (url, entry) in enumerate(selected.items(), start=1):
        source = RegulatorySource(source_id=f"register_{hashlib.sha256(url.encode()).hexdigest()[:12]}",
                                  source_name=entry.title, url=url, source_type=SourceType.DOCUMENT,
                                  regulatory_topics=["lending"], parser_strategy="rbi_document")
        check, _ = monitor.check_source(source)
        if check.error:
            failures.append(f"{url}: {check.status.value} {check.error}")
        time.sleep(PAUSE_SECONDS)
        print(f"predecessor {number}/{len(selected)} {check.status.value}", flush=True)

    withdrawn_by_register = apply_register(ingestion, entries, clock.now())
    linking = LinkingService(ingestion, settings).reconcile()
    documents = ingestion.list_documents()
    report = {
        "built_at": clock.now().isoformat(),
        "vector_backend": settings.vector_backend,
        "documents": len(documents),
        "lifecycle_counts": dict(Counter(item.lifecycle.value for item in documents)),
        "directions_from_pdfs": len(directions),
        "predecessors_selected": len(selected),
        "withdrawn_by_register": len(withdrawn_by_register),
        "linking": asdict(linking),
        "failures": failures,
        "register_decisions": [{"number": entry.number, "title": entry.title, "issued": str(entry.issued),
                                "included": included, "reason": reason} for entry, included, reason in decisions],
    }
    out = ROOT / "data" / "corpus" / "build-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "register_decisions"}, indent=2))


if __name__ == "__main__":
    main()
