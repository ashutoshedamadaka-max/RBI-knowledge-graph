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

    def __init__(self, content_id: str | None = None) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.content_id = content_id
        self._stack: list[tuple[str, bool, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        parent_active = self._stack[-1][1] if self._stack else self.content_id is None
        parent_ignored = self._stack[-1][2] if self._stack else False
        active = parent_active or (attributes.get("id") or "").lower() == self.content_id
        ignored = parent_ignored or tag in {"script", "style", "noscript", "nav", "header", "footer"}
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self._stack.append((tag, active, ignored))
        if active and not ignored and tag in {"p", "br", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        active = self._stack[-1][1] if self._stack else self.content_id is None
        ignored = self._stack[-1][2] if self._stack else False
        if active and not ignored and tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        active = self._stack[-1][1] if self._stack else self.content_id is None
        ignored = self._stack[-1][2] if self._stack else False
        if active and not ignored:
            self.parts.append(data)

    def text(self) -> str:
        text = unescape("".join(self.parts))
        text = re.sub(r"[\t \r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()


def extract_html_text(value: str) -> str:
    """Return readable RBI page text without scripts, styles, or page chrome."""
    # RBI's notification body has a stable container on both legacy and new pages.
    # Select it before parsing so site navigation cannot become evidence.
    match = re.search(r'\bid\s*=\s*["\'](NotificationUser)["\']', value, re.I)
    extractor = _RbiHtmlTextExtractor(match.group(1).lower() if match else None)
    extractor.feed(value)
    return extractor.text()


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
            text = extract_html_text(text)
        if not text:
            raise IngestionError("HTML document contains no readable text.")
        return ParsedDocument(page_count=1, pages=[text.strip()])
    raise IngestionError("Only PDF, HTML, TXT, and Markdown sources are supported in Phase 1.")
