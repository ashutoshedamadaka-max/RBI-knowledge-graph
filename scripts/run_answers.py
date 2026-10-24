"""Phase 5: answer quality on the question set, through the live query path (ADR-026) and a real model.

    python scripts/run_answers.py --corpus-dir data/runtime/corpus-v2 --model gpt-4o-mini
    python scripts/run_answers.py --corpus-dir data/runtime/corpus-v2 --model gpt-4o-mini --final   (test split)

Scored against gold only, never against another model's opinion:
  - answerable questions: the answer cites the gold sentence (per gold sentence and per question);
    wrongly refused;
  - withdrawn traps: the answer cites the withdrawn sentence (it must not);
  - unanswerable questions: refused (no grounded answer).
The claim checker's verdict on every claim is recorded too, but it is reported as the checker's view until
the checker is validated against Ashu's labels. Every rate has a 95% bootstrap interval (2,000 resamples of
questions, seed 7). Token use and cost go to the spend ledger. The test split runs only with --final, and
every such run is appended to data/evaluation/test-split-ledger.jsonl.
"""
import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.settings import Settings  # noqa: E402
from app.evaluation.retrieval_metrics import contains, same_page  # noqa: E402
from app.llm import claim_checker  # noqa: E402
from app.retrieval.query_service import RegulatoryQueryService  # noqa: E402

PRICES = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00)}  # USD per million input / output tokens, OpenAI list
ANSWERABLE = {"single_fact", "applies_to", "multi_hop", "change_over_time", "false_premise"}


def interval(values: list[float], seed: int = 7, resamples: int = 2000) -> dict:
    """Mean with a 95% percentile bootstrap interval over questions."""
    if not values:
        return {"value": None, "n": 0}
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(resamples))
    return {"value": round(sum(values) / len(values), 4), "low": round(means[int(0.025 * resamples)], 4),
            "high": round(means[int(0.975 * resamples) - 1], 4), "n": len(values)}


def cites(response, sentence: dict) -> bool:
    return any(same_page(chunk.source_url, sentence["url"]) and contains(chunk.text, sentence["span"])
               for chunk in response.retrieved_evidence if chunk.chunk_id in {c.chunk_id for c in response.citations})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini", choices=sorted(PRICES))
    parser.add_argument("--final", action="store_true", help="Run the held-out test split (logged).")
    parser.add_argument("--limit", type=int, help="Only the first N questions (a dry run).")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    split = "test" if args.final else "dev"
    questions_file = ROOT / "data" / "evaluation" / "v2" / f"{split}.jsonl"
    questions = [json.loads(line) for line in questions_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = [row for row in questions if row["status"] != "rejected"][:args.limit]
    input_rate, output_rate = PRICES[args.model]
    settings = Settings(data_dir=args.corpus_dir, vector_backend="filesystem", database_url=None,
                        answer_provider="openai", openai_answer_model=args.model,
                        openai_input_cost_per_million=input_rate, openai_output_cost_per_million=output_rate)
    if not (settings.openai_api_key and settings.cohere_api_key):
        sys.exit("OPENAI_API_KEY and COHERE_API_KEY are both needed (the approved path re-ranks with Cohere).")
    service = RegulatoryQueryService(settings)
    service.retriever.rerank_waits = (0, 10, 20, 40, 60, 60)  # a trial Cohere key is rate-limited per minute
    # The claim checker runs inside the live path with settings.openai_extraction_model (ADR-030).

    records = []
    for number, question in enumerate(questions, start=1):
        day = date.fromisoformat(question["as_of"]) if question.get("as_of") else None
        started = time.perf_counter()
        try:
            response = service.query(question["question"], as_of=day)
        except Exception as exc:  # recorded as a failed question, never skipped silently
            records.append({"id": question["id"], "type": question["type"], "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        latency = round((time.perf_counter() - started) * 1000)
        grounded = response.research is not None and response.research.status.value == "grounded"
        record = {"id": question["id"], "type": question["type"], "answered": grounded, "latency_ms": latency,
                  "answer_cost_usd": response.estimated_cost_usd, "answer_mode": response.pipeline.answer_mode if response.pipeline else None,
                  "notices": [item.kind for item in response.notices],
                  "steps": response.pipeline.retrieval_method if response.pipeline else None}
        if question["gold"]:
            record["gold_cited"] = [cites(response, sentence) for sentence in question["gold"]]
        if question["must_not_cite"]:
            record["cited_withdrawn"] = any(cites(response, sentence) for sentence in question["must_not_cite"])
        if grounded:
            # The live path already checked every claim (ADR-030); that cost is inside answer_cost_usd.
            passages = {chunk.chunk_id: chunk for chunk in response.retrieved_evidence}
            record["claims"] = [{"text": claim.text, "verdict": claim.support or "not_checked",
                                 "cited": [{"chunk_id": cid, "title": passages[cid].document_title, "text": passages[cid].text}
                                           for cid in claim.citation_ids if cid in passages]}
                                for claim in claim_checker.claims_of(response.research)]
        records.append(record)
        print(f"{number}/{len(questions)} {question['id']} {question['type']} answered={grounded}", flush=True)

    answer_cost = sum(record.get("answer_cost_usd") or 0 for record in records)
    checker_cost = 0.0  # since ADR-030 the live path checks claims; the cost is part of each answer's cost
    by_type = defaultdict(list)
    for record in records:
        by_type[record["type"]].append(record)

    def rate(rows, test) -> dict:
        return interval([1.0 if test(row) else 0.0 for row in rows])

    answerable = [row for row in records if row["type"] in ANSWERABLE and "error" not in row]
    claims = [claim for row in records for claim in row.get("claims", [])]
    report = {
        "generated_at": datetime.now(UTC).isoformat(), "split": split, "questions": len(questions),
        "model": args.model, "checker_model": settings.openai_extraction_model,
        "includes_unreviewed_drafts": any(row["status"] == "drafted" for row in questions),
        "failed_questions": [row["id"] for row in records if "error" in row],
        "questions_without_rerank": [row["id"] for row in records if "cohere_rerank" not in (row.get("steps") or "")],
        "results": {
            "gold_sentence_cited": interval([float(hit) for row in answerable for hit in row.get("gold_cited", [])]),
            "question_all_gold_cited": rate(answerable, lambda row: all(row.get("gold_cited", [False]))),
            "answerable_wrongly_refused": rate(answerable, lambda row: not row["answered"]),
            "withdrawn_trap_cited_withdrawn": rate(by_type["withdrawn_trap"], lambda row: row.get("cited_withdrawn", False)),
            "unanswerable_refused": rate(by_type["unanswerable"], lambda row: not row.get("answered", True)),
            "claims_by_checker (not yet validated)": dict(Counter(claim["verdict"] for claim in claims)),
            "by_type": {kind: {"questions": len(rows),
                               "answered": sum(1 for row in rows if row.get("answered")),
                               **({"gold_sentence_cited": interval([float(hit) for row in rows for hit in row.get("gold_cited", [])])}
                                  if kind in ANSWERABLE else {})}
                        for kind, rows in sorted(by_type.items())},
            "latency_ms_p50": sorted(row["latency_ms"] for row in records if "latency_ms" in row)[len(records) // 2] if records else None,
            "cost_usd": {"answers_including_claim_check": round(answer_cost, 4),
                         # Each answer's cost already includes the query embedding and the reported re-ranking charge
                         # (live pipeline events, Oct 2026), so nothing is added here; the key name is kept for the dashboard.
                         "per_question_answer_plus_rerank": round(answer_cost / max(len(records), 1), 5)},
        },
        "records": records,
        "run_manifest": {
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "working_tree_dirty": bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "app",
                                                       "scripts", "config"], cwd=ROOT, capture_output=True, text=True).stdout.strip()),
            "questions_sha256": hashlib.sha256(questions_file.read_bytes()).hexdigest(),
            "graph_sha256": hashlib.sha256((args.corpus_dir / "graph" / "graph.json").read_bytes()).hexdigest(),
            "abstain_below": settings.abstain_below, "rerank_candidates": settings.rerank_candidates,
        },
    }
    out = args.out or ROOT / "data" / "evaluation" / f"answers-{split}-{args.model}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (ROOT / "data" / "evaluation" / "spend-ledger.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": datetime.now(UTC).isoformat(), "phase": 5, "task": f"answers ({split})",
                                 "model": args.model, "checker_model": settings.openai_extraction_model, "questions": len(questions),
                                 "estimated_cost_usd": round(answer_cost + checker_cost, 6),
                                 "note": "Cohere re-ranking on a trial key: no charge."}) + "\n")
    if args.final:
        with (ROOT / "data" / "evaluation" / "test-split-ledger.jsonl").open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({"at": datetime.now(UTC).isoformat(), "model": args.model, "out": out.name,
                                     "git_commit": report["run_manifest"]["git_commit"]}) + "\n")
    print(json.dumps({key: value for key, value in report["results"].items() if key != "by_type"}, indent=2))


if __name__ == "__main__":
    main()
