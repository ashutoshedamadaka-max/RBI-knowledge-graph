"""Match each paragraph of a replaced document to the closest paragraph of its successor.

For the "what changed" view. Similarity is the rung-0 hashing-vector cosine (lexical, not
semantic); below a floor a paragraph is reported as having no close match rather than forced
onto one. Accuracy is not yet measured: present it as an automatic match.
"""

from dataclasses import dataclass

from app.embeddings.hashing import HashingEmbedder
from app.ingestion.chunkers import segment

NO_CLOSE_MATCH = 0.3  # ponytail: fixed floor, tune once a labelled sample exists


@dataclass(frozen=True)
class ParagraphMatch:
    old_paragraph: str
    new_paragraph: str | None
    similarity: float
    old_text: str
    new_text: str | None


def map_paragraphs(old_pages: list[str], new_pages: list[str]) -> list[ParagraphMatch]:
    embedder = HashingEmbedder()
    old = [unit for unit in segment(old_pages) if unit.label.isdigit()]
    new = [(unit, embedder.embed(" ".join(unit.lines))) for unit in segment(new_pages) if unit.label.isdigit()]
    matches = []
    for unit in old:
        text = "\n".join(unit.lines)
        vector = embedder.embed(text)
        best, score = max(((candidate, embedder.similarity(vector, embedding)) for candidate, embedding in new),
                          key=lambda pair: pair[1], default=(None, 0.0))
        close = best is not None and score >= NO_CLOSE_MATCH
        matches.append(ParagraphMatch(unit.label, best.label if close else None, round(score, 3), text,
                                      "\n".join(best.lines) if close else None))
    return matches
