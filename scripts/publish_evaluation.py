"""Publish a manifest-backed deterministic benchmark, without touching production.

Unlike the legacy bootstrap-only run, check *all* curated documents through the
production monitor. Configured approvals apply normally; unknown sources are not
manually approved and explicit withdrawal evidence still takes precedence.
"""
import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.settings import Settings
from app.evaluation.harness import EvaluationHarness
from app.ingestion.service import IngestionService
from app.ingestion.repair import repair_legacy_notifications
from app.models.documents import DocumentLifecycle
from app.monitoring.fetcher import RbiHttpFetcher
from app.monitoring.processor import MonitoringDocumentProcessor
from app.monitoring.registry import RegulatorySourceRegistry
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore


def fingerprint(paths):
    return {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('data/evaluation/current-report.json'))
    parser.add_argument('--offline', action='store_true', help='Use an existing snapshot; explicitly record no source refresh.')
    args = parser.parse_args()
    # Do not load production secrets, durable DB state or model settings.
    settings = Settings(_env_file=None, data_dir=args.data_dir, database_url=None, answer_provider='deterministic', extraction_provider='deterministic')
    dataset = ROOT / 'data/evaluation/rbi-lending-questions.json'
    ingestion = IngestionService(settings)
    repair_legacy_notifications(ingestion)
    checks = []
    if not args.offline:
        monitor = RegulatoryMonitor(MonitoringStore(settings.runtime_dir / 'monitoring.json'), RbiHttpFetcher(), MonitoringDocumentProcessor(ingestion))
        for source in RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources():
            if source.parser_strategy == 'rbi_document':
                result, _ = monitor.check_source(source)
                checks.append(result.model_dump(mode='json'))
                print(f'{source.source_id}: {result.status.value}', flush=True)
    else:
        latest = {}
        for check in MonitoringStore(settings.runtime_dir / 'monitoring.json').checks():
            latest[check.source_id] = check.model_dump(mode='json')
        checks = list(latest.values())
    ingestion.cleanup_duplicate_sources()
    documents = ingestion.list_documents()
    if not documents:
        raise SystemExit('No documents available: refusing to publish an empty-corpus benchmark.')
    report = EvaluationHarness(settings).run(EvaluationHarness.load_cases(dataset))
    payload = report.model_dump(mode='json')
    git = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(['git','status','--porcelain'], cwd=ROOT, capture_output=True, text=True)
    counts = Counter(document.lifecycle.value for document in documents)
    payload['run_manifest'] = {
        'git_commit': git.stdout.strip() if git.returncode == 0 else None,
        'working_tree_dirty': bool(dirty.stdout.strip()),
        'timestamp': datetime.now(UTC).isoformat(),
        'source_refresh_attempted': not args.offline,
        'source_checks': checks,
        'corpus_document_count': len(documents),
        'lifecycle_status_counts': {status.value: counts[status.value] for status in DocumentLifecycle},
        'top_k': settings.vector_top_k,
        'chunk_size': settings.chunk_size, 'chunk_overlap': settings.chunk_overlap,
        'extraction_provider': settings.extraction_provider,
        'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
        'code_sha256': fingerprint([*ROOT.glob('app/**/*.py'), ROOT/'scripts/publish_evaluation.py', ROOT/'config/regulatory_sources.yaml']),
        'corpus_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(settings.runtime_dir.glob('*.json')) if path.name in {'documents.json','vectors.json','knowledge_graph.json'}},
        'documents': [{'document_id': doc.document_id, 'source_url': doc.source_url, 'lifecycle': doc.lifecycle.value} for doc in documents],
        'limitations': ['Deterministic generation: not live OpenAI answer quality, cost or latency.',
                       'Citation mapping is not semantic claim verification.',
                       'Historical questions permit prior material; exact as-of authority is not reconstructed.',
                       'Existing benchmark labels retained, including sources no longer eligible for current guidance.'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k not in {'results','run_manifest'}}, indent=2))


if __name__ == '__main__':
    main()
