from dataclasses import dataclass
from pathlib import Path

import fitz

from app.ingestion.exceptions import IngestionError


@dataclass(frozen=True)
class ParsedDocument:
    page_count: int
    pages: list[str]


def parse_document(path: Path, mime_type: str) -> ParsedDocument:
    if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
        try:
            with fitz.open(path) as pdf:
                pages = [page.get_text("text").strip() for page in pdf]
        except (fitz.FileDataError, RuntimeError) as exc:
            raise IngestionError(f"Unable to parse PDF: {exc}") from exc
        if not any(pages):
            raise IngestionError("PDF contains no extractable text; OCR is not enabled.")
        return ParsedDocument(page_count=len(pages), pages=pages)
    if mime_type.startswith("text/") or path.suffix.lower() in {".txt", ".md"}:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionError("Text document must be UTF-8 encoded.") from exc
        if not text.strip():
            raise IngestionError("Document contains no text.")
        return ParsedDocument(page_count=1, pages=[text.strip()])
    raise IngestionError("Only PDF, TXT, and Markdown sources are supported in Phase 1.")

