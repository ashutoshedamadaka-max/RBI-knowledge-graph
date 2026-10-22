"""Phase 3: the abstention threshold (tuned on dev only) and the router measured as a classifier.

    python scripts/tune_abstention.py

Abstention: refuse when the scope guard says the question is not about RBI lending, or when the
re-ranker's top relevance score is below a threshold. Every threshold is scored on dev:
  - correct refusals: unanswerable questions refused;
  - wrong refusals: answerable questions (with a gold sentence) refused.
Withdrawn-trap questions are left out: the right behaviour there is to point to the replacement, not to refuse.
The threshold is the one with the highest balanced accuracy (the mean of the share of unanswerable
questions refused and the share of answerable ones answered); on a tie, the lowest threshold. This
rule was fixed before looking at the scores.

Router: QueryRouter's choice against the question type. Only two-paragraph (multi_hop) questions need
the graph (the Phase 4 graph rung helped only those), so GRAPH or HYBRID is right for them and VECTOR
for the rest.
Writes data/evaluation/abstention-dev.json.
"""
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.retrieval.router import QueryRouter  # noqa: E402
from app.retrieval.scope import is_rbi_lending_question  # noqa: E402

LADDER = ROOT / "data" / "evaluation" / "ladder-abstention-dev.json"
DEV = ROOT / "data" / "evaluation" / "v2" / "dev.jsonl"


def balanced(rows: list[dict], threshold: float, guard: bool = True) -> dict:
    refused = [row for row in rows if (guard and not row["in_scope"]) or row["top_score"] < threshold]
    unanswerable = [row for row in rows if not row["answerable"]]
    answerable = [row for row in rows if row["answerable"]]
    correct = sum(1 for row in refused if not row["answerable"])
    wrong = sum(1 for row in refused if row["answerable"])
    return {"threshold": threshold,
            "unanswerable_refused": {"numerator": correct, "denominator": len(unanswerable)},
            "answerable_refused": {"numerator": wrong, "denominator": len(answerable)},
            "balanced_accuracy": round((correct / len(unanswerable) + 1 - wrong / len(answerable)) / 2, 4)}


def main() -> None:
    report = json.loads(LADDER.read_text(encoding="utf-8"))
    questions = {row["id"]: row for row in map(json.loads, DEV.read_text(encoding="utf-8").splitlines()) if row}
    (name, result), = report["results"].items()
    rows = [{**item, "in_scope": is_rbi_lending_question(questions[item["id"]]["question"])}
            for item in result["per_question"] if item["type"] != "withdrawn_trap"]
    curve = [balanced(rows, threshold) for threshold in sorted({0.0} | {row["top_score"] for row in rows} | {1.01})]
    best = max(curve, key=lambda point: (point["balanced_accuracy"], -point["threshold"]))

    router = QueryRouter()
    confusion = Counter()
    for question in questions.values():
        route = router.route(question["question"]).route.value
        expected = "graph" if question["type"] == "multi_hop" else "vector"
        confusion[(expected, "graph" if route in {"GRAPH", "HYBRID"} else "vector")] += 1
    correct = confusion[("graph", "graph")] + confusion[("vector", "vector")]

    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scores_from": f"{LADDER.name} rung {name} ({report['models']['cohere']})",
        "includes_unreviewed_drafts": report["includes_unreviewed_drafts"],
        "chosen": best, "curve": curve,
        "scope_guard_alone": balanced(rows, 0.0),
        # Found on the first run: the keyword scope guard refuses 21 of 92 answerable questions, so the
        # curve is also reported without it (a finding for the gate, not a change to the rule above).
        "curve_without_scope_guard": [balanced(rows, point["threshold"], guard=False) for point in curve],
        "router": {"accuracy": {"numerator": correct, "denominator": sum(confusion.values())},
                   "confusion (expected -> routed)": {f"{e} -> {r}": n for (e, r), n in sorted(confusion.items())}},
        "run_manifest": {"ladder_sha256": hashlib.sha256(LADDER.read_bytes()).hexdigest(),
                         "dev_questions_sha256": hashlib.sha256(DEV.read_bytes()).hexdigest()},
    }
    (ROOT / "data" / "evaluation" / "abstention-dev.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({key: out[key] for key in ("chosen", "scope_guard_alone", "router")}, indent=2))


if __name__ == "__main__":
    main()
