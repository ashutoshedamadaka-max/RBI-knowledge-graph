"""The claim checker (Phase 5): a separate model call that judges each claim against the passages it cites.

It sees only the claim and its cited passages, never the question, the other claims or the evidence
the answer did not cite, so a claim stands or falls on its own citations. Its verdicts are validated
against Ashu's labels before any answer metric relies on them.
"""
import json

import httpx

from app.evaluation.questions import normalise
from app.models.chunks import ChunkMetadata
from app.models.research import StructuredResearch

VERDICTS = ("supported", "partially_supported", "not_supported")
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdicts"],
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["claim", "verdict", "quote"],
        "properties": {"claim": {"type": "integer"}, "verdict": {"type": "string", "enum": list(VERDICTS)},
                       "quote": {"type": "string"}}}}},
}
INSTRUCTIONS = (
    "You check claims in an answer about RBI regulations against the passages each claim cites. For every claim, "
    "decide from its own cited passages only, not from general knowledge:\n"
    "- supported: the passages state everything the claim says (paraphrase is fine);\n"
    "- partially_supported: some of the claim is stated, but part is missing, broader or more specific than the passages;\n"
    "- not_supported: the passages do not state the claim, or contradict it.\n"
    "quote: the shortest passage text that supports the claim, copied exactly; empty if not_supported.\n"
    "A passage marked WITHDRAWN does not support a claim about current rules."
)


def claims_of(research: StructuredResearch) -> list:
    return ([research.direct_answer] if research.direct_answer else []) + [
        claim for section in research.sections for claim in section.claims]


def check(api_key: str, model: str, research: StructuredResearch, evidence: list[ChunkMetadata]) -> tuple[list[dict], dict]:
    """One verdict per claim (in claims_of order) and the call's token usage. A claim without citations is
    not_supported without a model call; a quote that is not in the cited passages downgrades a support verdict."""
    passages = {chunk.chunk_id: chunk for chunk in evidence}
    claims = claims_of(research)
    blocks, verdicts = [], [None] * len(claims)
    for number, claim in enumerate(claims, start=1):
        cited = [passages[cid] for cid in claim.citation_ids if cid in passages]
        if not cited:
            verdicts[number - 1] = {"verdict": "not_supported", "quote": "", "reason": "no valid citation"}
            continue
        sources = "\n".join(f"[{chunk.chunk_id}] {chunk.document_title} ({chunk.lifecycle.value})\n{chunk.text}" for chunk in cited)
        blocks.append(f"CLAIM {number}: {claim.text}\nCITED PASSAGES:\n{sources}")
    usage = {}
    if blocks:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions", timeout=90,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "temperature": 0,
                  "messages": [{"role": "system", "content": INSTRUCTIONS},
                               {"role": "user", "content": "\n\n".join(blocks)}],
                  "response_format": {"type": "json_schema",
                                      "json_schema": {"name": "claim_verdicts", "strict": True, "schema": SCHEMA}}},
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        for item in json.loads(body["choices"][0]["message"]["content"])["verdicts"]:
            index = item["claim"] - 1
            if 0 <= index < len(claims) and verdicts[index] is None:
                cited_text = normalise(" ".join(passages[cid].text for cid in claims[index].citation_ids if cid in passages))
                verdict = item["verdict"]
                if verdict != "not_supported" and (not item["quote"].strip() or normalise(item["quote"]) not in cited_text):
                    verdict, reason = "partially_supported" if verdict == "supported" else verdict, "quote not in passages"
                else:
                    reason = None
                verdicts[index] = {"verdict": verdict, "quote": item["quote"], **({"reason": reason} if reason else {})}
    # A claim the checker skipped is not assumed to be supported.
    return [item or {"verdict": "not_supported", "quote": "", "reason": "checker returned no verdict"} for item in verdicts], usage
