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
                page_url=html.unescape(link.group(1)) if link else None,
                keys=tuple(item.key for item in find_references(number)),
            ))
    return entries


def apply_register(ingestion: IngestionService, entries: list[RegisterEntry], checked_at: datetime) -> list[str]:
    """Withdraw every current corpus document the register lists. Returns their document IDs.

    Matched by any printed reference number, or by the RBI page address. A document that is
    already withdrawn, repealed or superseded keeps its status and evidence.
    """
    by_key = {key: entry for entry in entries for key in entry.keys}
    by_url = {DocumentManifest.source_key(entry.page_url): entry for entry in entries if entry.page_url}
    withdrawn = []
    for document in ingestion.list_documents():
        if document.lifecycle in NON_OPERATIVE:
            continue
        entry = next((by_key[key] for key in document.circular_numbers if key in by_key), None)
        if entry is None and document.source_url:
            entry = by_url.get(DocumentManifest.source_key(document.source_url))
        if entry is None:
            continue
        ingestion.set_lifecycle(
            document.document_id, DocumentLifecycle.WITHDRAWN, REGISTER_URL,
            f"Listed in RBI's register of withdrawn circulars. {entry.quote}", checked_at, METHOD,
        )
        withdrawn.append(document.document_id)
    return withdrawn
