"""Quoted LLM extraction of APPLIES_TO and REQUIRES edges, one provision per call (Phase 4).

The model picks entities from config/graph/entities.yaml and must quote the provision for every
edge. Edges whose quote is not in the provision, or whose entity is not on the list, are dropped
and counted, never silently repaired.
"""
import json
import re
from pathlib import Path

import httpx
import yaml

from app.evaluation.questions import normalise

ENTITIES_FILE = Path(__file__).resolve().parents[2] / "config" / "graph" / "entities.yaml"
PRICES = {"gpt-4o-mini": (0.15, 0.60)}  # USD per million input / output tokens, OpenAI list price
MIN_QUOTE = 12
_DEFINITIONS = re.compile(r"following definitions|definitions\s*:|unless the context otherwise requires", re.IGNORECASE)


def load_entities(path: Path = ENTITIES_FILE) -> dict[str, dict]:
    """{id: {"type": RegulatedEntity | Product, "name": ..., "aliases": [...]}}"""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {key: {"type": kind, **value} for kind, rows in data.items() for key, value in rows.items()}


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 -]", " ", text.lower())).strip()


def resolve(name: str, entities: dict[str, dict]) -> str | None:
    """An entity id from an id, a name or an alias; None if it is not on the list."""
    key = _key(name)
    for entity_id, entity in entities.items():
        if key in {_key(entity_id), _key(entity["name"])} | {_key(alias) for alias in entity["aliases"]}:
            return entity_id
    return None


SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["applies_to", "requires"],
    "properties": {
        "applies_to": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["entity", "quote", "confidence"],
            "properties": {"entity": {"type": "string"}, "quote": {"type": "string"}, "confidence": {"type": "number"}}}},
        "requires": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["obligation", "bearer", "quote", "confidence"],
            "properties": {"obligation": {"type": "string"}, "bearer": {"type": "string"}, "quote": {"type": "string"},
                           "confidence": {"type": "number"}}}},
    },
}


def prompt(title: str, heading: str, text: str, entities: dict[str, dict]) -> str:
    listing = "\n".join(f"- {key}: {value['name']} ({value['type']})" for key, value in entities.items())
    return (
        "You read one provision of an RBI lending regulation and record two kinds of facts.\n"
        "applies_to: the regulated entities and loan products this provision governs. Use only ids from the list. "
        "The document title names who it is addressed to; do not add other kinds of lender unless the provision names "
        "them. Only include an entity or product the provision itself names or plainly addresses; not everything mentioned. "
        "List each entity at most once.\n"
        "requires: each obligation the provision imposes ('shall', 'must', 'is required to', 'shall not'); 'may' grants a permission and is not an obligation. obligation is "
        "a short plain summary (at most 15 words); bearer is the id of who must comply (from the list).\n"
        "In RBI documents 'the Reserve Bank', 'RBI' and 'the Bank' mean the regulator: never list it, and what the "
        "Reserve Bank may do is not an obligation. Definitions, headings and table rows impose no obligation.\n"
        "Every quote must be copied exactly, character for character, from the provision: the shortest clause that "
        "shows the fact. confidence is between 0 and 1. Return empty lists if there is nothing.\n\n"
        f"ENTITY LIST\n{listing}\n\nDOCUMENT: {title}\nPROVISION (under: {heading or 'no heading'})\n{text}"
    )


def extract(api_key: str, model: str, title: str, heading: str, text: str, entities: dict[str, dict]) -> tuple[dict, dict]:
    """The model's JSON and the token usage of the call."""
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions", timeout=90,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "temperature": 0,
              "messages": [{"role": "user", "content": prompt(title, heading, text, entities)}],
              "response_format": {"type": "json_schema",
                                  "json_schema": {"name": "provision_facts", "strict": True, "schema": SCHEMA}}},
    )
    response.raise_for_status()
    body = response.json()
    return json.loads(body["choices"][0]["message"]["content"]), body.get("usage", {})


def validate(raw: dict, text: str, entities: dict[str, dict]) -> tuple[list[dict], dict[str, int]]:
    """Edges that pass both checks, and a count of every reason an edge was dropped."""
    edges, dropped = [], {}
    source = normalise(text)
    definitions = bool(_DEFINITIONS.search(text[:300]))

    def keep(kind: str, entity: str, quote: str, confidence: float, **extra) -> None:
        entity_id = resolve(entity, entities)
        reason = None
        if len(quote.strip()) < MIN_QUOTE or normalise(quote) not in source:
            reason = "quote_not_in_provision"
        elif entity_id is None:
            reason = "entity_not_on_list"
        elif kind == "REQUIRES" and definitions:
            reason = "definitions_paragraph"
        if reason:
            dropped[f"{kind}:{reason}"] = dropped.get(f"{kind}:{reason}", 0) + 1
            return
        edges.append({"type": kind, "entity": entity_id, "quote": quote.strip(),
                      "confidence": max(0.0, min(1.0, float(confidence))), **extra})

    seen = set()
    for item in raw.get("applies_to", []):
        entity_id = resolve(item["entity"], entities)
        if entity_id and entity_id in seen:
            dropped["APPLIES_TO:duplicate"] = dropped.get("APPLIES_TO:duplicate", 0) + 1
            continue
        seen.add(entity_id)
        keep("APPLIES_TO", item["entity"], item["quote"], item["confidence"])
    for item in raw.get("requires", []):
        keep("REQUIRES", item["bearer"], item["quote"], item["confidence"], obligation=item["obligation"].strip())
    return edges, dropped
