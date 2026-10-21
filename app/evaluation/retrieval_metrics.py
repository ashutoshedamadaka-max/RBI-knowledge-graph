"""Retrieval scores against chunker-independent gold: an exact RBI sentence on a known page."""

from app.evaluation.questions import normalise
from app.ingestion.manifest import DocumentManifest


def contains(chunk_text: str, span: str) -> bool:
    return normalise(span) in normalise(chunk_text)


def same_page(chunk_url: str | None, gold_url: str) -> bool:
    return bool(chunk_url) and DocumentManifest.source_key(chunk_url) == DocumentManifest.source_key(gold_url)


def first_hit_rank(results: list, gold: dict) -> int | None:
    """1-based rank of the first retrieved chunk from the gold page that contains the whole gold sentence."""
    return next((rank for rank, chunk in enumerate(results, start=1)
                 if same_page(chunk.source_url, gold["url"]) and contains(chunk.text, gold["span"])), None)


def boundary_kept(chunks: list, gold: dict) -> bool:
    """Whether some chunk of the gold page holds the whole gold sentence (the chunker did not cut it)."""
    return any(same_page(chunk.source_url, gold["url"]) and contains(chunk.text, gold["span"]) for chunk in chunks)


def summarise(ranks: list[int | None], k_values=(5, 10)) -> dict:
    """recall@k and mean reciprocal rank over gold sentences (None = not found in the results)."""
    total = len(ranks)
    out = {f"recall@{k}": {"value": round(sum(1 for r in ranks if r and r <= k) / total, 4) if total else None,
                           "numerator": sum(1 for r in ranks if r and r <= k), "denominator": total} for k in k_values}
    out["mrr"] = round(sum(1 / r for r in ranks if r) / total, 4) if total else None
    return out
