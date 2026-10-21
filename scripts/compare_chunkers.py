"""Phase 2 gate: compare the chunkers on the reviewed dev questions, everything else held equal.

    python scripts/compare_chunkers.py --corpus-dir data/runtime/corpus-v1

For each chunker the same stored document text is chunked and indexed (no network), then every
reviewed dev question runs through the same baseline search (rung 0, status filter off: this
measures chunking, the status filter is a Phase 3 step). Reports boundary accuracy, recall@5,
recall@10 and MRR, overall and by question type, with a run manifest. Writes
data/evaluation/chunker-comparison.json. The held-out test split is never read.
"""
import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.settings import Settings  # noqa: E402
from app.evaluation.retrieval_metrics import boundary_kept, first_hit_rank, summarise  # noqa: E402
from app.ingestion.chunkers import count_tokens  # noqa: E402
from app.ingestion.chunking import chunk_document  # noqa: E402
from app.ingestion.manifest import DocumentManifest  # noqa: E402
from app.ingestion.parser import parse_document  # noqa: E402
from app.retrieval.vector_store import LocalVectorStore  # noqa: E402

CHUNKERS = ["legacy", "fixed", "recursive", "structure"]
RETRIEVE = 10


def load_questions(folder: Path, include_drafted: bool) -> list[dict]:
    rows = [json.loads(line) for line in (folder / "dev.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    usable = {"accepted", "edited"} | ({"drafted"} if include_drafted else set())
    return [row for row in rows if row["status"] in usable and row["gold"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, default=ROOT / "data" / "evaluation" / "v2")
    parser.add_argument("--include-drafted", action="store_true", help="Also use unreviewed drafts (dry runs only).")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data" / "runtime" / "chunker-comparison")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "evaluation" / "chunker-comparison.json")
    args = parser.parse_args()

    questions = load_questions(args.questions, args.include_drafted)
    if not questions:
        sys.exit("No reviewed dev questions with gold sentences yet: run scripts/review_questions.py first.")
    documents = DocumentManifest(args.corpus_dir / "runtime" / "documents.json").all()
    # Re-parse each stored original with the current parser, so a parser fix is always measured.
    def parse(document):
        raw = next((args.corpus_dir / "raw").glob(f"{document.document_id}.*"))
        return parse_document(raw, document.mime_type).pages
    pages = {document.document_id: parse(document) for document in documents}

    results = {}
    for name in CHUNKERS:
        settings = Settings(_env_file=None, data_dir=args.work_dir / name, chunker=name, vector_backend="filesystem")
        if (args.work_dir / name).exists():
            shutil.rmtree(args.work_dir / name)
        store = LocalVectorStore(settings.runtime_dir / "vectors.json")
        chunks = [chunk for document in documents for chunk in chunk_document(document, pages[document.document_id], settings)]
        store.upsert(chunks)
        ranks, kept, by_type = [], [], defaultdict(list)
        for question in questions:
            found = store.search(question["question"], top_k=RETRIEVE, current_only=False)
            for gold in question["gold"]:
                rank = first_hit_rank(found, gold)
                ranks.append(rank)
                by_type[question["type"]].append(rank)
                kept.append(boundary_kept(chunks, gold))
        tokens = [chunk.token_count or count_tokens(chunk.text) for chunk in chunks]  # same tokenizer for every chunker
        results[name] = {
            "chunks": len(chunks), "median_tokens": statistics.median(tokens),
            "boundary_accuracy": {"value": round(sum(kept) / len(kept), 4), "numerator": sum(kept), "denominator": len(kept)},
            **summarise(ranks),
            "by_type": {kind: summarise(values) for kind, values in sorted(by_type.items())},
        }
        print(name, json.dumps({key: value for key, value in results[name].items() if key != "by_type"}), flush=True)

    overlaps = [question["word_overlap"] for question in questions if question.get("word_overlap") is not None]
    dev_file = args.questions / "dev.jsonl"
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "questions": len(questions), "gold_sentences": sum(len(question["gold"]) for question in questions),
        "includes_unreviewed_drafts": args.include_drafted,
        "question_word_overlap_median": statistics.median(overlaps) if overlaps else None,
        "retriever": "rung 0 (hashing + keyword blend), status filter off, top 10",
        "results": results,
        "run_manifest": {
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "working_tree_dirty": bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "app",
                                                       "scripts", "config"], cwd=ROOT, capture_output=True, text=True).stdout.strip()),
            "corpus_fingerprint": hashlib.sha256("".join(sorted(f"{d.document_id}:{d.content_hash}" for d in documents))
                                                 .encode()).hexdigest(),
            "dev_questions_sha256": hashlib.sha256(dev_file.read_bytes()).hexdigest(),
        },
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
