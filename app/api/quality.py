"""Numbers for the quality dashboard, read only from saved evaluation runs (brief rule: never invent a metric).

Each entry is a saved file under data/evaluation/; a file that does not exist is reported as not yet measured.
Large per-question records are trimmed to the failures, which the dashboard's failure gallery shows.
"""
import json
from pathlib import Path

EVALUATION = Path(__file__).resolve().parents[2] / "data" / "evaluation"
SOURCES = {
    "answers_test": "answers-test-gpt-4o-mini.json",
    "answers_dev": "answers-dev-gpt-4o-mini.json",
    "answers_dev_first_prompt": "answers-dev-gpt-4o-mini-prompt1.json",
    "ladder": "ladder-dev.json",
    "graph_on_off": "ladder-graph-dev.json",
    "abstention": "abstention-dev.json",
    "graph_quality": "graph-quality.json",
    "graph_build": "graph-build.json",
    "claim_checker": "claim-checker-quality.json",
    "replay": "replay-report.json",
    "chunkers": "chunker-comparison-provisional.json",
}
ANSWERABLE = {"single_fact", "applies_to", "multi_hop", "change_over_time", "false_premise"}


def failures(records: list[dict], limit: int = 12) -> list[dict]:
    """Real failed cases: answerable but refused or missing the gold sentence, a withdrawn rule cited, an
    unanswerable question answered, or a claim the checker did not pass."""
    out = []
    for record in records:
        reasons = []
        if record.get("error"):
            reasons.append("the question failed to run")
        if record["type"] in ANSWERABLE and not record.get("answered"):
            reasons.append("answerable, but refused")
        elif record["type"] in ANSWERABLE and not all(record.get("gold_cited", [True])):
            reasons.append("did not cite the gold sentence")
        if record.get("cited_withdrawn"):
            reasons.append("cited a withdrawn rule")
        if record["type"] == "unanswerable" and record.get("answered"):
            reasons.append("answered a question the corpus cannot answer")
        flagged = [claim for claim in record.get("claims", []) if claim["verdict"] != "supported"]
        if reasons or flagged:
            out.append({"id": record["id"], "type": record["type"], "reasons": reasons,
                        "flagged_claims": [{"text": claim["text"], "verdict": claim["verdict"]} for claim in flagged[:2]]})
    return out[:limit]


def spend() -> dict:
    ledger = EVALUATION / "spend-ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.exists() else []
    by_phase: dict[str, float] = {}
    for row in rows:
        by_phase[str(row.get("phase"))] = by_phase.get(str(row.get("phase")), 0.0) + (row.get("estimated_cost_usd") or 0.0)
    return {"total_usd": round(sum(by_phase.values()), 4), "by_phase_usd": {key: round(value, 4) for key, value in by_phase.items()},
            "entries": len(rows), "note": "From the spend ledger; Cohere re-ranking ran on a free trial key."}


def quality_report() -> dict:
    report = {}
    for name, file_name in SOURCES.items():
        path = EVALUATION / file_name
        if not path.exists():
            report[name] = {"status": "not yet measured", "file": file_name}
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "records" in data:
            data = {**{key: value for key, value in data.items() if key != "records"}, "failures": failures(data["records"])}
        report[name] = {"status": "measured", "file": file_name, "data": data}
    report["spend"] = spend()
    return report
