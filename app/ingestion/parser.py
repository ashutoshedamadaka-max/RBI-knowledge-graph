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
        # Amendment pages display deleted wording alongside the replacement.
        # Do not flatten that visual distinction into an operative requirement.
        struck_out = bool(re.search(r"text-decoration(?:-line)?\s*:[^;]*line-through", attributes.get("style") or "", re.I))
        ignored = parent_ignored or struck_out or tag in {"script", "style", "noscript", "nav", "header", "footer", "s", "strike", "del"}
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


FOOTNOTE_MARKER = re.compile(r"\[\^\d{1,3}\]")
_SMALL = 0.85     # a span this much smaller than the page's body text is a superscript or footnote
_FOOTER = 0.72    # footnotes sit in the bottom part of the page


def _pdf_page_text(page) -> str:
    """Page text with footnote markers as [^n] and footnotes moved to the end as "[^n]: text".

    RBI directions use footnotes for amendment history ("Inserted with effect from July 01, 2026 vide
    ... Amendment Directions"). Plain extraction turns a marker into a stray digit inside the sentence
    and mixes the footnote into the body; reading font sizes keeps them apart.
    """
    blocks = page.get_text("dict")["blocks"]
    spans = [span for block in blocks for line in block.get("lines", []) for span in line["spans"] if span["text"].strip()]
    if not spans:
        return ""
    sizes = {}
    for span in spans:
        sizes[round(span["size"], 1)] = sizes.get(round(span["size"], 1), 0) + len(span["text"])
    body = max(sizes, key=sizes.get)  # the size most text is printed in
    footer_top = page.rect.height * _FOOTER
    page_lines = []
    for block in blocks:
        for line in block.get("lines", []):
            parts = [span for span in line["spans"] if span["text"]]
            visible = [span for span in parts if span["text"].strip()]
            text = "".join(span["text"] for span in parts)
            near_edge = not (0.08 * page.rect.height < line["bbox"][1] < 0.9 * page.rect.height)
            if not visible or (near_edge and re.fullmatch(r"\s*\d{1,3}\s*", text)):
                continue  # the printed page number, which would otherwise land inside a sentence
            page_lines.append((line, parts, all(span["size"] < body * _SMALL for span in visible)))
    # Markers first: a small number inside a body line. Only a numbered footer line whose number is
    # marked on this page is a footnote; small-print table rows near the bottom stay where they are.
    markers = {span["text"].strip() for _, parts, small in page_lines if not small for span in parts
               if span["text"].strip().isdigit() and span["size"] < body * _SMALL}
    lines, notes, in_note = [], [], False
    for line, parts, small in page_lines:
        text = "".join(span["text"] for span in parts)
        if small and line["bbox"][1] >= footer_top:
            number = re.match(r"\s*(\d{1,3})\s+(.*)", text)
            if number and number.group(1) in markers:
                notes.append(f"[^{number.group(1)}]: {number.group(2).strip()}")
                in_note = True
                continue
            if in_note and not number:  # a footnote running onto a second line
                notes[-1] += " " + text.strip()
                continue
        in_note = False
        if not small:
            text = "".join(f"[^{span['text'].strip()}]" if span["text"].strip() in markers
                           and span["size"] < body * _SMALL else span["text"] for span in parts)
        lines.append(text)
    return "\n".join(lines + notes)


def parse_document(path: Path, mime_type: str) -> ParsedDocument:
    if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
        try:
            with fitz.open(path) as pdf:
                pages = [_pdf_page_text(page).strip() for page in pdf]
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
