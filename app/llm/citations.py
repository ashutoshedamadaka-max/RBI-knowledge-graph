import re

from app.models.chunks import ChunkMetadata
from app.models.research import StructuredResearch


CITATION_PATTERN = re.compile(r"\[(chunk_[a-f0-9]{20})\]")


def extract_citation_ids(answer: str) -> list[str]:
    return CITATION_PATTERN.findall(answer)


def validate_citations(answer: str, retrieved_chunks: list[ChunkMetadata]) -> bool:
    cited = extract_citation_ids(answer)
    available = {chunk.chunk_id for chunk in retrieved_chunks}
    return bool(cited) and set(cited).issubset(available)


def validate_structured_citations(research: StructuredResearch, retrieved_chunks: list[ChunkMetadata]) -> bool:
    if research.status.value != "grounded":
        return not research.sections and (not research.direct_answer or not research.direct_answer.citation_ids)
    claims = ([research.direct_answer] if research.direct_answer else []) + [
        claim for section in research.sections for claim in section.claims
    ]
    if not claims or any(not claim or not claim.citation_ids for claim in claims):
        return False
    available = {chunk.chunk_id for chunk in retrieved_chunks}
    return all(set(claim.citation_ids).issubset(available) for claim in claims if claim)
