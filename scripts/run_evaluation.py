import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings
from app.evaluation.harness import EvaluationHarness
from app.ingestion.service import IngestionService
from app.models.documents import DocumentLifecycle, IngestRequest
from app.monitoring.fetcher import RbiHttpFetcher
from app.monitoring.processor import MonitoringDocumentProcessor
from app.monitoring.registry import RegulatorySourceRegistry
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore


def bootstrap_curated_corpus(settings) -> int:
    """Build an isolated, deterministic evaluation corpus from the curated RBI pages."""
    service = IngestionService(settings)
    sources = [
        source for source in RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources()
        if source.parser_strategy == "rbi_document"
    ]
    for source in sources:
        service.ingest(IngestRequest(source_url=str(source.url), title=source.source_name))
    return len(sources)


def lifecycle_counts(settings) -> dict[str, int]:
    """Return the latest indexed document count by lifecycle for one evaluation corpus."""
    documents = IngestionService(settings).list_documents()
    counts = Counter(document.lifecycle.value for document in documents)
    return {lifecycle.value: counts[lifecycle.value] for lifecycle in DocumentLifecycle}


def apply_curated_approvals(settings) -> list[str]:
    """Run the production curated-approval path against the isolated corpus.

    This intentionally delegates to RegulatoryMonitor rather than mutating document
    statuses. RBI lifecycle evidence still overrides an approval, exactly as it
    does during monitoring.
    """
    sources = [
        source for source in RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources()
        if source.approved_lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED}
    ]
    monitor = RegulatoryMonitor(
        MonitoringStore(settings.runtime_dir / "monitoring.json"),
        RbiHttpFetcher(),
        MonitoringDocumentProcessor(IngestionService(settings)),
    )
    for source in sources:
        monitor.check_source(source)
    return [source.source_id for source in sources]


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate vector-only retrieval against routed Graph RAG.")
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/rbi-lending-questions.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/portfolio-report.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/evaluation/corpus"))
    parser.add_argument("--bootstrap-curated", action="store_true", help="Download the curated RBI lending pages before evaluation.")
    parser.add_argument(
        "--apply-curated-approvals", action="store_true",
        help="Run existing monitoring approval logic for configured curated sources before evaluation.",
    )
    args = parser.parse_args()

    base = get_settings()
    settings = base.model_copy(update={
        "data_dir": args.data_dir,
        "database_url": None,
        "answer_provider": "deterministic",
    })
    bootstrap_completed_at = None
    if args.bootstrap_curated:
        print(f"Bootstrapping {bootstrap_curated_corpus(settings)} curated RBI lending sources…")
        bootstrap_completed_at = datetime.now(UTC)
        print(f"Lifecycle counts after bootstrap: {lifecycle_counts(settings)}")
    approved_source_ids: list[str] = []
    if args.apply_curated_approvals:
        approved_source_ids = apply_curated_approvals(settings)
        print(f"Lifecycle counts after curated approvals: {lifecycle_counts(settings)}")
    harness = EvaluationHarness(settings)
    report = harness.run(harness.load_cases(args.dataset), benchmark_id=args.dataset.stem)
    payload = report.model_dump(mode="json")
    payload["run_manifest"] = {
        "git_commit": git_commit(),
        "bootstrap_completed_at": bootstrap_completed_at.isoformat() if bootstrap_completed_at else None,
        "corpus_document_count": sum(lifecycle_counts(settings).values()),
        "lifecycle_status_counts": lifecycle_counts(settings),
        "curated_approvals_applied": args.apply_curated_approvals,
        "curated_approval_source_ids": approved_source_ids,
        "source_retrieval": {
            "pass_count": report.source_retrieval_pass_count,
            "evaluable_count": report.source_retrieval_evaluable_count,
            "pass_rate": (
                report.source_retrieval_pass_count / report.source_retrieval_evaluable_count
                if report.source_retrieval_evaluable_count else None
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    print(json.dumps({key: value for key, value in payload.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
