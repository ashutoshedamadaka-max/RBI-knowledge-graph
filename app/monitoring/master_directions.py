"""Read RBI's Master Directions index and decide which entries belong in the corpus.

The index on www.rbi.org.in is readable automatically. The directions' text is only in
PDFs on rbidocs.rbi.org.in, which shows automated clients a CAPTCHA, so those PDFs are
downloaded by a person and matched back to their index entry by file name. Each PDF file
name is unique to one version, so a changed name (or a changed "Updated as on" date) means
RBI has amended the direction in place.
"""

import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from app.corpus.identifiers import parse_date

INDEX_URL = "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx"
PAGE_URL = "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id={page_id}"

_ROW = re.compile(r"<tr>\s*<td>\s*<a[^>]*href=[\"']?\s*BS_ViewMasDirections\.aspx\?id=(\d+)[^>]*>(.*?)</a>(.*?)</tr>",
                  re.IGNORECASE | re.DOTALL)
_PDF = re.compile(r"href=[\"']([^\"']+\.pdf)[\"']", re.IGNORECASE)
_SIZE = re.compile(r">\s*([\d.]+)\s*kb\s*<", re.IGNORECASE)
_UPDATED = re.compile(r"\((?:updated|as updated) as on ([^)]+)\)", re.IGNORECASE)


@dataclass(frozen=True)
class IndexEntry:
    page_id: str
    title: str
    pdf_url: str | None
    size_kb: float | None
    updated_as_on: date | None

    @property
    def page_url(self) -> str:
        return PAGE_URL.format(page_id=self.page_id)

    @property
    def pdf_file_name(self) -> str | None:
        return self.pdf_url.rsplit("/", 1)[-1] if self.pdf_url else None


def parse_index(page: str) -> list[IndexEntry]:
    entries: dict[str, IndexEntry] = {}
    for page_id, title, rest in _ROW.findall(page):
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title))).strip()
        pdf, size, updated = _PDF.search(rest), _SIZE.search(rest), _UPDATED.search(title)
        entries.setdefault(page_id, IndexEntry(
            page_id=page_id, title=title, pdf_url=pdf.group(1) if pdf else None,
            size_kb=float(size.group(1)) if size else None,
            updated_as_on=parse_date(updated.group(1)) if updated else None,
        ))
    return list(entries.values())


@dataclass(frozen=True)
class InclusionDecision:
    entry: IndexEntry
    included: bool
    reason: str


def decide_inclusion(entries: list[IndexEntry], rule_path: Path) -> list[InclusionDecision]:
    """Apply the written inclusion rule (ADR-013) to index entries, with a reason for each."""
    rule = yaml.safe_load(rule_path.read_text(encoding="utf-8"))["master_directions"]
    decisions = []
    for entry in entries:
        entity = next((name for name in rule["entities"] if name.lower() in entry.title.lower()), None)
        topic = next((name for name in rule["topics"] if name.lower() in entry.title.lower()), None)
        if entity is None:
            decisions.append(InclusionDecision(entry, False, "regulated entity outside the corpus scope"))
        elif topic is None:
            decisions.append(InclusionDecision(entry, False, f"{entity}: title names no lending topic in the rule"))
        else:
            decisions.append(InclusionDecision(entry, True, f"{entity}: lending topic '{topic}'"))
    return decisions
