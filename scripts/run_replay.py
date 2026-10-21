"""Run the Phase 1 historical replay and write the gate report.

    python scripts/run_replay.py --source-dir data/runtime/corpus-v1 --register-file <saved register page>

Writes data/evaluation/replay-report.json with a run manifest (brief rule 4). The replay
itself runs in data/runtime/replay (rebuilt each time) on the file index, so it never
touches the corpus in PostgreSQL.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.settings import Settings  # noqa: E402
from app.ingestion.manifest import DocumentManifest  # noqa: E402
from app.models.documents import DocumentLifecycle  # noqa: E402
from app.monitoring.withdrawn_register import REGISTER_URL, parse_register  # noqa: E402
from app.replay import run_replay  # noqa: E402

LABELS = ROOT / "data" / "evaluation" / "gold" / "phase1_labels.json"


def withdrawal_detection(documents, register_page: str) -> dict:
    """The page watermark (what the monitor reads) scored against RBI's register (independent)."""
    entries = parse_register(register_page)
    keys = {key for entry in entries for key in entry.keys}
    urls = {DocumentManifest.source_key(entry.page_url) for entry in entries if entry.page_url}
    listed = {item.document_id for item in documents
              if set(item.circular_numbers) & keys or (item.source_url and DocumentManifest.source_key(item.source_url) in urls)}
    detected = {item.document_id for item in documents if item.lifecycle is DocumentLifecycle.WITHDRAWN
                and item.status_resolution_method == "AUTOMATED"}
    return {
        "recall": {"value": round(len(listed & detected) / len(listed), 4) if listed else None,
                   "numerator": len(listed & detected), "denominator": len(listed)},
        "false_alarms": len(detected - listed),
        "listed_but_not_detected": sorted(listed - detected),
        "note": "Predecessors were selected from the register, so every one is listed; recall tests the watermark "
                "detector, false alarms test the 16 current directions.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--register-file", type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--auto-trust", choices=["on", "off"], default="on")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "evaluation" / "replay-report.json")
    args = parser.parse_args()

    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    source = Settings(_env_file=None, data_dir=args.source_dir)
    documents = DocumentManifest(source.runtime_dir / "documents.json").all()
    register = (args.register_file.read_text(encoding="utf-8") if args.register_file
                else httpx.get(REGISTER_URL, follow_redirects=True, timeout=90).text)

    report = run_replay(args.source_dir, ROOT / "data" / "runtime" / "replay", labels, args.today,
                        auto_trust_enabled=args.auto_trust == "on")
    report["withdrawal_detection"] = withdrawal_detection(documents, register)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "app", "scripts", "config"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    report["run_manifest"] = {
        "git_commit": commit, "working_tree_dirty": dirty,
        "corpus_fingerprint": hashlib.sha256("".join(sorted(f"{d.document_id}:{d.content_hash}" for d in documents))
                                             .encode()).hexdigest(),
        "lifecycle_counts": dict(Counter(item.lifecycle.value for item in documents)),
        "labels_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        "labels_answered": {key: sum(value is not None for value in answers.values())
                            for key, answers in labels.items() if isinstance(answers, dict)},
        "register_sha256": hashlib.sha256(register.encode()).hexdigest(),
        "settings": {"auto_trust_enabled": args.auto_trust == "on", "vector_backend": "filesystem",
                     "answer_provider": "deterministic", "chunk_size": source.chunk_size,
                     "chunk_overlap": source.chunk_overlap, "top_k": source.vector_top_k},
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"answers", "assumptions"}}, indent=2))


if __name__ == "__main__":
    main()
