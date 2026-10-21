"""Draft the Phase 2 question set for Ashu to review (ADR-021).

    OPENAI_API_KEY in .env or the environment (.env is git-ignored; never commit a key)
    python scripts/draft_questions.py --corpus-dir data/runtime/corpus-v1
    python scripts/draft_questions.py --corpus-dir data/runtime/corpus-v1 --offline   (no model, for testing)

Writes data/evaluation/v2/dev.jsonl and test.jsonl (status "drafted"; review with
scripts/review_questions.py) and appends token usage and cost to data/evaluation/spend-ledger.jsonl.
Drafts whose evidence is not an exact quote of the source paragraph are discarded and counted.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.settings import Settings  # noqa: E402
from app.evaluation.questions import OfflineDrafter, OpenAIDrafter, paragraph_pool, plan, to_item  # noqa: E402
from app.observability.costs import estimate_openai_cost  # noqa: E402

OUT = ROOT / "data" / "evaluation" / "v2"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if any(args.out.glob("*.jsonl")):
        sys.exit(f"{args.out} already has questions; drafting again would change the held-out split. Move them first.")

    settings = Settings()
    if args.offline:
        drafter = OfflineDrafter()
    elif not settings.openai_api_key:
        sys.exit("Put OPENAI_API_KEY in .env (or the environment), or use --offline.")
    else:
        drafter = OpenAIDrafter(settings.openai_api_key, settings.openai_extraction_model)
        drafter.model = settings.openai_extraction_model

    current = {row["page_url"] for row in json.loads((ROOT / "data" / "source_pdfs" / "manifest.json")
                                                     .read_text(encoding="utf-8"))["directions"]}
    report = json.loads((ROOT / "data" / "corpus" / "build-report.json").read_text(encoding="utf-8"))
    topics = sorted({row["title"] for row in report["register_decisions"] if "excluded topic" in row["reason"]})
    planned = plan(paragraph_pool(args.corpus_dir, current), topics)

    items, discarded, tokens = [], Counter(), Counter()
    for number, entry in enumerate(planned, start=1):
        try:
            draft = drafter.draft(entry["type"], entry["sources"], entry["as_of"])
        except Exception as exc:  # report and continue
            discarded[f"{entry['type']}: drafting failed ({type(exc).__name__})"] += 1
            continue
        tokens.update({key: draft.pop("usage", {}).get(key, 0) for key in ("prompt_tokens", "completion_tokens")})
        item = to_item(number, entry, draft, drafter.model)
        if item is None:
            discarded[f"{entry['type']}: evidence not an exact quote"] += 1
            continue
        items.append(item)
        print(f"{number}/{len(planned)} {entry['type']}", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    for split in ("dev", "test"):
        rows = [item for item in items if item["split"] == split]
        (args.out / f"{split}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    cost = estimate_openai_cost(tokens["prompt_tokens"], tokens["completion_tokens"],
                                settings.openai_input_cost_per_million, settings.openai_output_cost_per_million)
    if args.offline:  # no model calls, nothing spent
        print(json.dumps({"drafted": len(items), "discarded": discarded}, indent=2))
        return
    with (ROOT / "data" / "evaluation" / "spend-ledger.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": datetime.now(UTC).isoformat(), "phase": 2, "task": "draft questions",
                                 "model": drafter.model, **tokens, "estimated_cost_usd": cost}) + "\n")
    print(json.dumps({"drafted": len(items), "by_type": Counter(item["type"] for item in items),
                      "by_split": Counter(item["split"] for item in items), "discarded": discarded,
                      "estimated_cost_usd": cost}, indent=2))


if __name__ == "__main__":
    main()
