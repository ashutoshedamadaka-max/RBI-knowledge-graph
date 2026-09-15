import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.documents import DocumentMetadata


class DocumentManifest:
    """Local cache manifest; replaced by PostgreSQL metadata in Phase 2."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[DocumentMetadata]:
        if not self.path.exists():
            return []
        return [DocumentMetadata.model_validate(row) for row in json.loads(self.path.read_text())]

    def all(self) -> list[DocumentMetadata]:
        return self._read()

    def get_by_hash(self, content_hash: str) -> DocumentMetadata | None:
        return next((item for item in self._read() if item.content_hash == content_hash), None)

    def get_by_source_url(self, source_url: str | None) -> DocumentMetadata | None:
        """Return an existing record for the same authoritative source page."""
        if not source_url:
            return None
        expected = self._canonical_url(source_url)
        matches = [item for item in self._read() if item.source_url and self._canonical_url(item.source_url) == expected]
        if not matches:
            return None
        # A URL can retain historical fetched versions. Monitoring must update
        # the most recently assessed version, not whichever JSON row came first.
        return max(matches, key=lambda item: (item.status_checked_at or item.ingested_at, item.document_version, item.ingested_at))

    def save(self, document: DocumentMetadata) -> None:
        documents = [item for item in self._read() if item.document_id != document.document_id]
        documents.append(document)
        self.path.write_text(json.dumps([item.model_dump(mode="json") for item in documents], indent=2))

    def update_lifecycle(self, document_id: str, lifecycle, evidence_url: str, excerpt: str, checked_at) -> DocumentMetadata | None:
        documents = self._read()
        updated = None
        for index, document in enumerate(documents):
            if document.document_id == document_id:
                updated = document.model_copy(update={
                    "lifecycle": lifecycle,
                    "status_evidence_url": evidence_url,
                    "status_evidence_excerpt": excerpt,
                    "status_checked_at": checked_at,
                })
                documents[index] = updated
                break
        if updated:
            self.path.write_text(json.dumps([item.model_dump(mode="json") for item in documents], indent=2))
        return updated

    def update_monitoring_metadata(self, document_id: str, document_identifier: str | None, effective_date, checked_at) -> DocumentMetadata | None:
        documents = self._read()
        updated = None
        for index, document in enumerate(documents):
            if document.document_id == document_id:
                updated = document.model_copy(update={
                    "document_identifier": document_identifier or document.document_identifier,
                    "effective_date": effective_date or document.effective_date,
                    "last_checked_at": checked_at,
                })
                documents[index] = updated
                break
        if updated:
            self.path.write_text(json.dumps([item.model_dump(mode="json") for item in documents], indent=2))
        return updated

    def mark_not_current(self, document_id: str, valid_to) -> DocumentMetadata | None:
        documents = self._read()
        updated = None
        for index, document in enumerate(documents):
            if document.document_id == document_id:
                updated = document.model_copy(update={"is_current": False, "valid_to": valid_to})
                documents[index] = updated
                break
        if updated:
            self.path.write_text(json.dumps([item.model_dump(mode="json") for item in documents], indent=2))
        return updated

    def remove_document_ids(self, document_ids: set[str]) -> None:
        if not document_ids:
            return
        remaining = [item for item in self._read() if item.document_id not in document_ids]
        self.path.write_text(json.dumps([item.model_dump(mode="json") for item in remaining], indent=2))

    @staticmethod
    def _canonical_url(value: str) -> str:
        parsed = urlsplit(value)
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), query, ""))
