from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re

import fitz

from app.ingestion.exceptions import IngestionError


@dataclass(frozen=True)
class ParsedDocument:
    page_count: int
    pages: list[str]


class _RbiHtmlTextExtractor(HTMLParser):
    """Extract readable text from official RBI notification pages without a web-scraping dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        elif tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        text = unescape("".join(self.parts))
        text = re.sub(r"[\t \r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()


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
        if mime_type in {"text/html", "application/xhtml+xml"}:
            extractor = _RbiHtmlTextExtractor()
            extractor.feed(text)
            text = extractor.text()
        if not text:
            raise IngestionError("HTML document contains no readable text.")
        return ParsedDocument(page_count=1, pages=[text.strip()])
    raise IngestionError("Only PDF, HTML, TXT, and Markdown sources are supported in Phase 1.")
