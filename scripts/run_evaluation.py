import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings
from app.evaluation.harness import EvaluationHarness
from app.ingestion.service import IngestionService
from app.models.documents import IngestRequest
from app.monitoring.registry import RegulatorySourceRegistry


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate vector-only retrieval against routed Graph RAG.")
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/rbi-lending-questions.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/latest-results.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/evaluation/corpus"))
    parser.add_argument("--bootstrap-curated", action="store_true", help="Download the curated RBI lending pages before evaluation.")
    args = parser.parse_args()

    base = get_settings()
    settings = base.model_copy(update={
        "data_dir": args.data_dir,
        "database_url": None,
        "answer_provider": "deterministic",
    })
    if args.bootstrap_curated:
        print(f"Bootstrapping {bootstrap_curated_corpus(settings)} curated RBI lending sources…")
    harness = EvaluationHarness(settings)
    report = harness.run(harness.load_cases(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.model_dump(), indent=2))
    print(json.dumps(report.model_dump(exclude={"results"}), indent=2))


if __name__ == "__main__":
    main()
