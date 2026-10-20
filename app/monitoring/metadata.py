"""Conservative extraction of directly published RBI document metadata.

Only facts printed in the page header are read: the document's own reference
numbers, its date line, its title and an explicit effective date. Anything not
found stays empty rather than being guessed.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
import re

from app.corpus.identifiers import Reference, find_references, parse_date

# The document's own numbers appear near the top; later ones are citations.
_HEADER_SEARCH_CHARS = 3000
_DATE_LINE = re.compile(
    r"\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}\s*"
)
_SIZE_MARKER = re.compile(r"\s*\(\s*\d+(?:\.\d+)?\s*kb\s*\)\s*", re.IGNORECASE)
_FAQ_TITLE = re.compile(r"^\s*(FAQs? on\b.{5,200}?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class RbiDocumentFacts:
    document_identifier: str | None = None
    effective_date: date | None = None
    reference_numbers: list[str] = field(default_factory=list)
    issue_date: date | None = None
    issuing_department: str | None = None
    title: str | None = None
    document_type: str | None = None


def extract_rbi_document_facts(text: str) -> RbiDocumentFacts:
    own = _own_references(text)
    normalized = " ".join(text.split())
    effective = re.search(
        r"(?:come into effect|effective|applicable).{0,60}?\b(?:from|on)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        normalized,
        flags=re.IGNORECASE,
    )
    effective_date = None
    if effective:
        try:
            effective_date = datetime.strptime(effective.group(1), "%B %d, %Y").date()
        except ValueError:
            pass
    title = _title(text, own)
    rbi_numbers = [item.key for item in own if item.kind == "rbi"]
    return RbiDocumentFacts(
        document_identifier=(rbi_numbers or [item.key for item in own] or [None])[0],
        effective_date=effective_date,
        reference_numbers=[item.key for item in own],
        issue_date=_issue_date(text, own),
        issuing_department=next((item.department for item in own if item.kind != "rbi" and item.department),
                                next((item.department for item in own if item.department), None)),
        title=title,
        document_type=document_type(title),
    )


def document_type(title: str | None) -> str | None:
    """Classify by the title RBI prints; None when the title gives no clear signal."""
    if not title:
        return None
    lowered = title.lower()
    if re.search(r"\bfaqs?\b|frequently asked questions", lowered):
        return "faq"
    if re.search(r"\bamendment\b", lowered):
        return "amendment"
    if lowered.startswith("master direction"):
        return "master_direction"
    if lowered.startswith("master circular"):
        return "master_circular"
    if re.search(r"\bdirections?,?\s+\d{4}\b", lowered):
        return "directions"
    if re.search(r"\bregulations,?\s+\d{4}\b", lowered):
        return "regulations"
    return "circular"


def _own_references(text: str) -> list[Reference]:
    """The first reference in the header and any printed directly after it."""
    references = [item for item in find_references(text[:_HEADER_SEARCH_CHARS])]
    if not references:
        return []
    own = [references[0]]
    for item in references[1:]:
        if text[own[-1].end:item.start].strip():
            break
        own.append(item)
    return own


def _issue_date(text: str, own: list[Reference]) -> date | None:
    """The first line that is only a date, within a few lines after the numbers."""
    if not own:
        return None
    for line in text[own[-1].end:].splitlines()[:5]:
        if _DATE_LINE.fullmatch(line):
            return parse_date(line)
    return None


def _title(text: str, own: list[Reference]) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines[:15]):
        if _SIZE_MARKER.fullmatch(line) and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate and not find_references(candidate) and not candidate.isupper():
                return candidate
    faq = _FAQ_TITLE.search(text[:_HEADER_SEARCH_CHARS])
    if faq:
        return faq.group(1)
    if own:
        before = text[:own[0].start].rstrip().splitlines()
        if before and before[-1].strip() and not _SIZE_MARKER.fullmatch(before[-1]):
            return before[-1].strip()
    return None
