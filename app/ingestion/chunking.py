import hashlib
import re

from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentLifecycle, DocumentMetadata


def chunk_pages(document: DocumentMetadata, pages: list[str], chunk_size: int, overlap: int) -> list[ChunkMetadata]:
    """Split page text on word boundaries; chunks never cross a source page."""

    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap.")

    chunks: list[ChunkMetadata] = []
    for page_number, page_text in enumerate(pages, start=1):
        words = re.findall(r"\S+", page_text)
        start = 0
        page_index = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            text = " ".join(words[start:end])
            if text:
                identity = f"{document.document_id}:{page_number}:{page_index}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"
                chunks.append(ChunkMetadata(
                    chunk_id=f"chunk_{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
                    document_id=document.document_id,
                    document_title=document.title,
                    page_number=page_number,
                    chunk_index=page_index,
                    text=text,
                    source_url=document.source_url,
                    document_version=document.document_version,
                    is_current=document.is_current,
                    lifecycle=document.lifecycle,
                    authority_current=document.lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED},
                    valid_from=document.valid_from,
                    valid_to=document.valid_to,
                ))
                page_index += 1
            if end == len(words):
                break
            start = end - overlap
    return chunks
