"""Graph extraction quality against Ashu's labels on random provisions (Phase 4).

Labels are per provision: the entities it governs (APPLIES_TO), and which of its numbered sentences
impose an obligation (REQUIRES), define a term (DEFINES) or refer to another paragraph or RBI
document (REFERS_TO). An extracted edge counts for the sentence its quote falls in.
"""
import random
import re

from app.evaluation.questions import normalise

_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(“\"‘'\[])|\n(?=\s*\((?:[ivxlc]{1,6}|[a-z]|\d{1,2})\)\s)")
_LABEL_ONLY = re.compile(r"\d{1,3}(?:\.\d{1,2})*\.?")


def sentences(text: str) -> list[str]:
    """A provision split into sentences and list items, in order (the units Ashu labels)."""
    parts = []
    for part in (part.strip() for part in _SPLIT.split(text) if part and part.strip()):
        if parts and _LABEL_ONLY.fullmatch(parts[-1]):
            parts[-1] += " " + part  # "14." on its own is the paragraph number of what follows
        else:
            parts.append(part)
    return parts


def sentence_of(quote: str, parts: list[str]) -> set[int]:
    """1-based numbers of the sentences a quote falls in (a quote may span several)."""
    key = normalise(quote)
    hits = {number for number, part in enumerate(parts, start=1)
            if key[:40] in normalise(part) or normalise(part)[:40] in key}
    return hits


def sample(provisions: list[str], size: int, seed: int, exclude: set[str]) -> list[str]:
    pool = sorted(node for node in provisions if node not in exclude)
    return sorted(random.Random(seed).sample(pool, size))


def score(predicted: dict[str, set], gold: dict[str, set]) -> dict:
    """Micro precision and recall over provisions: sets of entity ids or sentence numbers per provision."""
    true_positive = sum(len(predicted.get(key, set()) & gold[key]) for key in gold)
    predicted_total = sum(len(predicted.get(key, set())) for key in gold)
    gold_total = sum(len(value) for value in gold.values())
    return {
        "precision": {"value": round(true_positive / predicted_total, 4) if predicted_total else None,
                      "numerator": true_positive, "denominator": predicted_total},
        "recall": {"value": round(true_positive / gold_total, 4) if gold_total else None,
                   "numerator": true_positive, "denominator": gold_total},
    }
