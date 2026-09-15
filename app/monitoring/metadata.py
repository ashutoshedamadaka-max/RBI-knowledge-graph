"""Conservative extraction of directly published RBI document metadata."""

from dataclasses import dataclass
from datetime import datetime
import re


@dataclass(frozen=True)
class RbiDocumentFacts:
    document_identifier: str | None = None
    effective_date: object | None = None


def extract_rbi_document_facts(text: str) -> RbiDocumentFacts:
    normalized = " ".join(text.split())
    identifier = re.search(r"\bRBI/\d{4}-\d{2}/\d+\b", normalized, flags=re.IGNORECASE)
    if not identifier:
        identifier = re.search(r"\b(?:DoR|DOR)\.[A-Z0-9./-]{8,}\b", normalized, flags=re.IGNORECASE)
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
    return RbiDocumentFacts(
        document_identifier=identifier.group(0) if identifier else None,
        effective_date=effective_date,
    )
