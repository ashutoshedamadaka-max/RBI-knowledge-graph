"""Phase 2 question set: model-drafted from RBI paragraphs, verified by Ashu (ADR-021).

Gold is document-derived: an exact sentence of the source paragraph, its RBI page address and
paragraph number, so it can be found in the chunks of any chunker. The drafting model sees only
the source text, never retrieval results. Each question is assigned to dev or held-out test at
random when drafted, before any review or run.
"""

import json
import random
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from app.ingestion.chunkers import segment
from app.ingestion.manifest import DocumentManifest
from app.models.documents import DocumentLifecycle, DocumentMetadata

TARGETS = {"single_fact": 50, "applies_to": 30, "multi_hop": 30, "change_over_time": 30,
           "withdrawn_trap": 20, "unanswerable": 20, "false_premise": 20}
TEST_SHARE = 1 / 3
_APPLIES = re.compile(r"\b(?:shall apply|applicable to|apply to|shall be applicable)\b", re.IGNORECASE)
_CROSS_REFERENCE = re.compile(r"\bparagraphs?\s+(\d{1,3})\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]{3,}")

INSTRUCTIONS = {
    "single_fact": "Ask one specific factual question that this paragraph answers.",
    "applies_to": "Ask which entities, loans or situations this paragraph applies to.",
    "multi_hop": "Ask one question that needs BOTH paragraphs to answer. Put the sentence from the first "
                 "paragraph in evidence_span and the one from the second in second_evidence_span.",
    "change_over_time": "Ask what this rule required on the given date, mentioning that date in the question.",
    "withdrawn_trap": "Ask about this rule as if it applied today, without saying it was withdrawn.",
    "unanswerable": "Ask a specific question about this RBI topic. Leave evidence_span empty.",
    "false_premise": "Ask a question that assumes one fact from the paragraph is different (for example a wrong "
                     "number, entity or time limit). Put the true sentence in evidence_span and describe the "
                     "change in altered_fact.",
}


@dataclass(frozen=True)
class Paragraph:
    document: DocumentMetadata
    label: str
    text: str


def normalise(text: str) -> str:
    """Compare text without whitespace differences, letter case or footnote markers ([^3])."""
    return re.sub(r"\s+", " ", re.sub(r"\[\^\d{1,3}\]", "", text)).strip().lower()


def word_overlap(question: str, span: str) -> float:
    """Share of the question's words that also appear in the gold sentence (copying inflates retrieval)."""
    asked = set(_WORD.findall(question.lower()))
    return round(len(asked & set(_WORD.findall(span.lower()))) / len(asked), 3) if asked else 0.0


def paragraph_pool(corpus_dir: Path, current_urls: set[str]) -> dict[str, list[Paragraph]]:
    pool: dict[str, list[Paragraph]] = {"current": [], "withdrawn": []}
    for document in DocumentManifest(corpus_dir / "runtime" / "documents.json").all():
        processed = corpus_dir / "processed" / f"{document.document_id}.json"
        pages = [page["text"] for page in json.loads(processed.read_text(encoding="utf-8"))["pages"]]
        kind = "current" if document.source_url in current_urls else (
            "withdrawn" if document.lifecycle is DocumentLifecycle.WITHDRAWN else None)
        if kind is None:
            continue
        for unit in segment(pages):
            text = "\n".join(unit.lines)
            if unit.label.isdigit() and 200 < len(text) < 4000:
                pool[kind].append(Paragraph(document, unit.label, text))
    return pool


def plan(pool: dict[str, list[Paragraph]], excluded_topics: list[str], seed: int = 20261021,
         targets: dict[str, int] = TARGETS) -> list[dict]:
    """Which sources each question is drafted from, with its type, as-of date and split."""
    rng = random.Random(seed)
    current, withdrawn = pool["current"], pool["withdrawn"]
    by_doc = {}
    for paragraph in current:
        by_doc.setdefault(paragraph.document.document_id, {})[paragraph.label] = paragraph
    pairs = [(paragraph, by_doc[paragraph.document.document_id][match.group(1)])
             for paragraph in current for match in _CROSS_REFERENCE.finditer(paragraph.text)
             if match.group(1) in by_doc[paragraph.document.document_id] and match.group(1) != paragraph.label]
    sources = {
        "single_fact": [[item] for item in current],
        "applies_to": [[item] for item in current if _APPLIES.search(item.text)],
        "multi_hop": [list(pair) for pair in pairs],
        "change_over_time": [[item] for item in withdrawn if _as_of(item)],
        "withdrawn_trap": [[item] for item in withdrawn],
        "unanswerable": [[topic] for topic in excluded_topics],
        "false_premise": [[item] for item in current],
    }
    items = []
    for kind, count in targets.items():
        chosen = rng.sample(sources[kind], min(count, len(sources[kind])))
        tests = set(rng.sample(range(len(chosen)), round(len(chosen) * TEST_SHARE)))
        for index, source in enumerate(chosen):
            items.append({"type": kind, "split": "test" if index in tests else "dev", "sources": source,
                          "as_of": _as_of(source[0]) if kind == "change_over_time" else None})
    return items


def _as_of(paragraph: Paragraph) -> str | None:
    """A date when a withdrawn rule was still in force: midway through its life before 28 November 2025."""
    start = paragraph.document.in_force_from or paragraph.document.publication_date
    if not start or start >= date(2025, 11, 28):
        return None
    return date.fromordinal((start.toordinal() + date(2025, 11, 28).toordinal()) // 2).isoformat()


class OpenAIDrafter:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key, self.model = api_key, model

    def draft(self, kind: str, sources: list, as_of: str | None) -> dict:
        context = "\n\n".join(
            f"PARAGRAPH {index + 1} ({source.document.title}, paragraph {source.label}):\n{source.text}"
            if isinstance(source, Paragraph) else f"RBI TOPIC: {source}" for index, source in enumerate(sources))
        prompt = (
            f"You write evaluation questions for a tool that answers RBI lending-rule questions for an NBFC "
            f"compliance analyst. {INSTRUCTIONS[kind]} "
            + (f"The date is {as_of}. " if as_of else "")
            + "Write the question the way an analyst would ask it, in your own words: do not copy distinctive "
            "phrases from the paragraph. evidence_span must be copied exactly, character for character, from "
            "the paragraph: the shortest sentence or clause that answers the question. reference_answer is a "
            "one or two sentence correct answer.\n\n" + context
        )
        fields = ["question", "evidence_span", "second_evidence_span", "reference_answer", "altered_fact"]
        schema = {"type": "object", "additionalProperties": False, "required": fields,
                  "properties": {field: {"type": "string"} for field in fields}}
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions", timeout=60,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "temperature": 0.3, "messages": [{"role": "user", "content": prompt}],
                  "response_format": {"type": "json_schema",
                                      "json_schema": {"name": "question", "strict": True, "schema": schema}}},
        )
        response.raise_for_status()
        body = response.json()
        draft = json.loads(body["choices"][0]["message"]["content"])
        draft["usage"] = body.get("usage", {})
        return draft


class OfflineDrafter:
    """Deterministic stand-in for tests: asks about the first sentence of the first paragraph."""

    model = "offline"

    def draft(self, kind: str, sources: list, as_of: str | None) -> dict:
        if not isinstance(sources[0], Paragraph):
            return {"question": f"What does RBI require on {sources[0]}?", "evidence_span": "",
                    "second_evidence_span": "", "reference_answer": "Not covered by the corpus.", "altered_fact": ""}
        def first_sentence(text: str) -> str:
            return next((s for s in re.split(r"(?<=[.;:])\s+", text) if len(s.strip()) >= 25), text)
        sentence = first_sentence(sources[0].text)
        second = first_sentence(sources[1].text) if len(sources) > 1 else ""
        return {"question": f"What does paragraph {sources[0].label} of {sources[0].document.title} say?",
                "evidence_span": sentence, "second_evidence_span": second, "reference_answer": sentence,
                "altered_fact": "a number was changed" if kind == "false_premise" else ""}


def to_item(number: int, planned: dict, draft: dict, drafter_model: str) -> dict | None:
    """A reviewable question, or None when the draft's evidence is not an exact quote of its source."""
    sources = planned["sources"]
    gold = []
    for span, source in ((draft["evidence_span"], sources[0]), (draft.get("second_evidence_span", ""),
                                                                 sources[1] if len(sources) > 1 else None)):
        if isinstance(source, Paragraph):
            # An exact quote of the source, long enough to be a real sentence (not "50.").
            if len(span.strip()) < 25 or normalise(span) not in normalise(source.text):
                return None
            gold.append({"url": source.document.source_url, "document_title": source.document.title,
                         "paragraph": source.label, "span": span.strip()})
    kind = planned["type"]
    trap = gold if kind == "withdrawn_trap" else []
    return {
        "id": f"q{number:03d}", "type": kind, "split": planned["split"], "status": "drafted",
        "question": draft["question"].strip(), "as_of": planned["as_of"],
        "gold": [] if kind in {"withdrawn_trap", "unanswerable"} else gold,
        "must_not_cite": trap,
        "expected": {"withdrawn_trap": "say the rule was withdrawn or replaced; never cite it",
                     "unanswerable": "decline: the indexed RBI corpus does not cover this",
                     "false_premise": "correct the premise using the gold sentence"}.get(kind, "answer from the gold sentence"),
        "reference_answer": draft["reference_answer"].strip(),
        "altered_fact": draft.get("altered_fact", "").strip() or None,
        "topic": sources[0] if not isinstance(sources[0], Paragraph) else None,
        "word_overlap": word_overlap(draft["question"], " ".join(item["span"] for item in gold)) if gold else None,
        "drafter": drafter_model,
    }
