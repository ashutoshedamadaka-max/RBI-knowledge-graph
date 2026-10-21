"""Review the drafted Phase 2 questions: accept, edit or reject each one (ADR-021).

    python scripts/review_questions.py            dev questions first, then test
    python scripts/review_questions.py --split dev
    python scripts/review_questions.py --sample 30    a fixed random sample of dev, to measure draft quality

Each answer is saved straight away (stop with q and run again to resume). Only accepted or
edited questions are used in evaluation.
"""
import argparse
import json
import random
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.evaluation.questions import word_overlap  # noqa: E402

FOLDER = ROOT / "data" / "evaluation" / "v2"


def show(label: str, text: str) -> None:
    print(textwrap.fill(f"{label}: {text}", width=100, subsequent_indent="    "))


def update(path: Path, item_id: str, changes: dict) -> None:
    """Re-read the file and change only this question, so edits made elsewhere are not lost."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row["id"] == item_id:
            row.update(changes)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--folder", type=Path, default=FOLDER)
    parser.add_argument("--sample", type=int, help="Review only a random sample of this many dev questions.")
    args = parser.parse_args()
    sample = None
    if args.sample:
        # Drawn once (seed 3) and saved, so the sample is the same on every run and can be reported.
        record = args.folder / "review-sample.json"
        if not record.exists():
            ids = sorted(json.loads(line)["id"] for line in (args.folder / "dev.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
            record.write_text(json.dumps({"seed": 3, "ids": sorted(random.Random(3).sample(ids, args.sample))}, indent=2), encoding="utf-8")
        sample = set(json.loads(record.read_text(encoding="utf-8"))["ids"])
        args.split = "dev"
    for split in [args.split] if args.split else ["dev", "test"]:
        path = args.folder / f"{split}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        pending = [row for row in rows if row["status"] == "drafted" and (sample is None or row["id"] in sample)]
        print(f"\n{split}: {len(rows) - len(pending)} of {len(rows)} reviewed.")
        for number, row in enumerate(pending, start=1):
            print(f"\n[{split} {number}/{len(pending)}] {row['id']} — {row['type'].replace('_', ' ')}")
            show("Question", row["question"])
            if row["as_of"]:
                show("Asked as of", row["as_of"])
            for gold in row["gold"] or row["must_not_cite"]:
                show("Source", f"{gold['document_title']}, paragraph {gold['paragraph']} ({gold['url']})")
                show("Gold sentence" if row["gold"] else "Withdrawn sentence it must not cite", gold["span"])
            if row["topic"]:
                show("Topic outside the corpus", row["topic"])
            if row["altered_fact"]:
                show("Altered fact", row["altered_fact"])
            show("Reference answer", row["reference_answer"])
            show("Expected behaviour", row["expected"])
            choice = ""
            while choice not in {"a", "e", "r", "s", "q"}:
                choice = input("  [a = accept, e = edit, r = reject, s = skip, q = quit] ").strip().lower()
            if choice == "q":
                return
            if choice == "s":
                continue
            if choice == "r":
                update(path, row["id"], {"status": "rejected"})
                continue
            changes = {"status": "accepted"}
            if choice == "e":
                question = input("  New question (blank keeps it): ").strip()
                answer = input("  New reference answer (blank keeps it): ").strip()
                changes = {"status": "edited", **({"question": question} if question else {}),
                           **({"reference_answer": answer} if answer else {})}
                if question and row["gold"]:
                    changes["word_overlap"] = word_overlap(question, " ".join(gold["span"] for gold in row["gold"]))
            update(path, row["id"], changes)
    print("\nAll questions reviewed.")


if __name__ == "__main__":
    main()
