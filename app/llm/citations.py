import re

from app.models.chunks import ChunkMetadata


CITATION_PATTERN = re.compile(r"\[(chunk_[a-f0-9]{20})\]")


def extract_citation_ids(answer: str) -> list[str]:
    return CITATION_PATTERN.findall(answer)


def validate_citations(answer: str, retrieved_chunks: list[ChunkMetadata]) -> bool:
    cited = extract_citation_ids(answer)
    available = {chunk.chunk_id for chunk in retrieved_chunks}
    return bool(cited) and set(cited).issubset(available)

