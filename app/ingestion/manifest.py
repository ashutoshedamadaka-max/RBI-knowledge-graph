import json
from pathlib import Path

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

    def save(self, document: DocumentMetadata) -> None:
        documents = [item for item in self._read() if item.document_id != document.document_id]
        documents.append(document)
        self.path.write_text(json.dumps([item.model_dump(mode="json") for item in documents], indent=2))

