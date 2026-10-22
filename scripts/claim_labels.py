"""Phase 5 answer key for the claim checker: Ashu labels 50 random claims against the passages they cite.

    python scripts/claim_labels.py make  --answers data/evaluation/answers-dev-gpt-4o-mini.json
    python scripts/claim_labels.py read  --filled data/evaluation/gold/claim-labels-to-fill.md --source hand
    python scripts/claim_labels.py score --answers data/evaluation/answers-dev-gpt-4o-mini.json

make writes a fill-in document (the checker's verdict is never shown). read stores the answers in
data/evaluation/gold/claim-labels.json with their source ("hand", or "model-drafted, reviewed by Ashu").
score compares the checker's verdicts with the labels, per label source, and writes
data/evaluation/claim-checker-quality.json.
"""
import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "evaluation" / "gold" / "claim-labels.json"
FILL = ROOT / "data" / "evaluation" / "gold" / "claim-labels-to-fill.md"
SIZE, SEED = 50, 8
CODES = {"s": "supported", "p": "partially_supported", "n": "not_supported"}


def claim_id(record_id: str, number: int, text: str) -> str:
    return f"{record_id}/{number}/{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}"


def all_claims(answers: dict) -> dict[str, dict]:
    return {claim_id(record["id"], number, claim["text"]): claim
            for record in answers["records"] for number, claim in enumerate(record.get("claims", []), start=1)}


def make(answers_file: Path) -> None:
    claims = all_claims(json.loads(answers_file.read_text(encoding="utf-8")))
    chosen = sorted(random.Random(SEED).sample(sorted(claims), min(SIZE, len(claims))))
    out = ["# Claim labels", "",
           "Each claim comes from an answer the system wrote. Read the claim and the RBI passages it cites, then after "
           "`Verdict:` type one letter:", "",
           "- **s** (supported): the passages say everything the claim says (in other words is fine).",
           "- **p** (partly): some of it is in the passages, but part is missing, broader or more specific.",
           "- **n** (not supported): the passages don't say it, or say something different.", "",
           "Judge only from the passages shown, not from what you know about RBI rules. "
           "Please don't change the `ID:` lines.", ""]
    for number, key in enumerate(chosen, start=1):
        claim = claims[key]
        out += ["---", "", f"## Claim {number} of {len(chosen)}", "", f"ID: {key}", "", f"**Claim:** {claim['text']}", ""]
        for passage in claim["cited"]:
            out += [f"**Passage — {passage['title']}:**", "", "> " + passage["text"].replace("\n", "\n> "), ""]
        if not claim["cited"]:
            out += ["*(This claim cites no passage.)*", ""]
        out += ["Verdict: ", ""]
    FILL.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(chosen)} claims written to {FILL}")


def read(filled: Path, source: str) -> None:
    text = filled.read_text(encoding="utf-8")
    labels = {}
    for block in text.split("\n---")[1:]:
        key = re.search(r"^ID: (\S+)", block, re.M)
        verdict = re.search(r"^Verdict:\s*([spn])\b", block, re.M | re.I)
        if key and verdict:
            labels[key.group(1)] = {"label": CODES[verdict.group(1).lower()], "source": source,
                                    "labelled_at": datetime.now(UTC).isoformat()}
    data = json.loads(GOLD.read_text(encoding="utf-8")) if GOLD.exists() else {"seed": SEED, "labels": {}}
    data["labels"].update(labels)
    GOLD.write_text(json.dumps(data, indent=2), encoding="utf-8")
    missing = len(re.findall(r"^ID: ", text, re.M)) - len(labels)
    print(f"{len(labels)} labels saved ({source}); {missing} claims left without a verdict.")


def score(answers_file: Path) -> None:
    claims = all_claims(json.loads(answers_file.read_text(encoding="utf-8")))
    labels = json.loads(GOLD.read_text(encoding="utf-8"))["labels"]
    report = {"generated_at": datetime.now(UTC).isoformat(), "answers": answers_file.name, "by_source": {}}
    for source in sorted({item["source"] for item in labels.values()}, key=lambda value: value != "hand"):
        pairs = [(claims[key]["verdict"], item["label"]) for key, item in labels.items()
                 if item["source"] == source and key in claims]
        agree = sum(1 for checker, label in pairs if checker == label)
        # The decision that matters: does the checker flag the claims a person says are not fully supported?
        flagged = [(checker != "supported", label != "supported") for checker, label in pairs]
        caught = sum(1 for flag, bad in flagged if flag and bad)
        report["by_source"][source] = {
            "claims": len(pairs),
            "exact_agreement": {"numerator": agree, "denominator": len(pairs)},
            "unsupported_caught (recall)": {"numerator": caught, "denominator": sum(1 for _, bad in flagged if bad)},
            "flags_correct (precision)": {"numerator": caught, "denominator": sum(1 for flag, _ in flagged if flag)},
            "confusion (checker -> label)": {f"{c} -> {l}": n for (c, l), n in sorted(Counter(pairs).items())},
        }
    out = ROOT / "data" / "evaluation" / "claim-checker-quality.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["by_source"], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["make", "read", "score"])
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--filled", type=Path, default=FILL)
    parser.add_argument("--source", default="hand", choices=["hand", "model-drafted, reviewed by Ashu"])
    args = parser.parse_args()
    if args.action == "read":
        read(args.filled, args.source)
    elif not args.answers:
        sys.exit("--answers is required for make and score.")
    else:
        (make if args.action == "make" else score)(args.answers)


if __name__ == "__main__":
    main()
