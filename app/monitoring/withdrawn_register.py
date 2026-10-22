"""RBI's register of withdrawn circulars as official withdrawal evidence.

RBI lists every circular its Department of Regulation and Department of Supervision has
withdrawn, with number, title and date, on one HTML page (no CAPTCHA). It is the annex of
the 28 November 2025 consolidation (RBI/2025-26/100) and later withdrawals. A corpus
document whose printed number or page address is listed there is withdrawn: a negative
finding, which automation may make on its own. The register does not say what replaced a
circular; successors come from the documents themselves (app/monitoring/linking.py).
"""

import html
import re
from dataclasses import dataclass
from datetime import date, datetime

from app.corpus.identifiers import find_references, parse_date
from app.ingestion.manifest import DocumentManifest
from app.ingestion.service import IngestionService, NON_OPERATIVE
from app.models.documents import DocumentLifecycle

REGISTER_URL = "https://www.rbi.org.in/Scripts/NotificationUserWithdrawnCircular.aspx"
METHOD = "RBI_WITHDRAWN_REGISTER"
# RBI/2025-26/100 withdrew the circulars in its annex "with immediate effect" on this date.
CONSOLIDATION = date(2025, 11, 28)

_SECTION = re.compile(r"<h3[^>]*>\s*(Circulars Withdrawn by the Department of [^<]+?)\s*</h3>(.*?)</table>",
                      re.IGNORECASE | re.DOTALL)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_LINK = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)


@dataclass(frozen=True)
class RegisterEntry:
    section: str
    number: str
    title: str
    issued: date | None
    page_url: str | None
    keys: tuple[str, ...]

    @property
    def quote(self) -> str:
        return f"{self.section}: {self.number} — {self.title}, {self.issued.strftime('%B %d, %Y') if self.issued else 'undated'}"


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def parse_register(page: str) -> list[RegisterEntry]:
    entries = []
    for section, table in _SECTION.findall(page):
        for row in _ROW.findall(table):
            cells = _CELL.findall(row)
            if len(cells) != 4:
                continue
            link = _LINK.search(cells[1])
            number = _text(cells[1])
            entries.append(RegisterEntry(
                section=_text(section), number=number, title=_text(cells[2]), issued=parse_date(_text(cells[3])),
                page_url=html.unescape(link.group(1)).split("#", 1)[0] if link else None,
                keys=tuple(item.key for item in find_references(number)),
            ))
    return entries


def match_register(documents: list, entries: list[RegisterEntry]) -> dict[str, RegisterEntry]:
    """The register row for each listed document, by any printed reference number or the RBI page address."""
    by_key = {key: entry for entry in entries for key in entry.keys}
    by_url = {DocumentManifest.source_key(entry.page_url): entry for entry in entries if entry.page_url}
    matched = {}
    for document in documents:
        entry = next((by_key[key] for key in document.circular_numbers if key in by_key), None)
        if entry is None and document.source_url:
            entry = by_url.get(DocumentManifest.source_key(document.source_url))
        if entry is not None:
            matched[document.document_id] = entry
    return matched


def apply_register(ingestion: IngestionService, entries: list[RegisterEntry], checked_at: datetime) -> list[str]:
    """Withdraw every current corpus document the register lists. Returns their document IDs.

    A document that is already withdrawn, repealed or superseded keeps its status and evidence.
    """
    documents = ingestion.list_documents()
    matched = match_register(documents, entries)
    withdrawn = []
    for document in documents:
        entry = matched.get(document.document_id)
        if entry is None:
            continue
        if document.lifecycle not in NON_OPERATIVE:
            ingestion.set_lifecycle(
                document.document_id, DocumentLifecycle.WITHDRAWN, REGISTER_URL,
                f"Listed in RBI's register of withdrawn circulars. {entry.quote}", checked_at, METHOD,
            )
            withdrawn.append(document.document_id)
        # Issued before the consolidation: in force no later than 28 November 2025. Never extend a
        # window that a successor or an earlier withdrawal already closed sooner.
        issued = document.publication_date
        if issued and issued < CONSOLIDATION:
            current = ingestion.get(document.document_id)
            if current.in_force_to is None or current.in_force_to > CONSOLIDATION:
                ingestion.set_in_force(document.document_id, current.in_force_from, CONSOLIDATION)
    return withdrawn


def select_predecessors(entries: list[RegisterEntry], rule: dict) -> list[tuple[RegisterEntry, bool, str]]:
    """Apply the written rule (config/corpus/inclusion.yaml: withdrawn_circulars) with a reason per row."""
    decisions = []
    for entry in entries:
        title = entry.title.lower()
        excluded = next((word for word in rule["exclude_title_keywords"] if word.lower() in title), None)
        included = next((word for word in rule["include_title_keywords"] if word.lower() in title), None)
        if not entry.issued or entry.issued < rule["issued_since"]:
            decisions.append((entry, False, f"issued before {rule['issued_since']}"))
        elif excluded:
            decisions.append((entry, False, f"title names an excluded topic '{excluded}'"))
        elif not included:
            decisions.append((entry, False, "title names no lending topic"))
        elif not entry.page_url:
            decisions.append((entry, False, "register gives no RBI page to fetch"))
        else:
            decisions.append((entry, True, f"lending topic '{included}'"))
    return decisions
