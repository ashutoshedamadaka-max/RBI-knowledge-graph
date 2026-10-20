import hashlib
import json
from pathlib import Path

from app.models.links import DocumentLink, LinkTrust


def link_id_for(relation: str, old_document_id: str, new_document_id: str, method: str) -> str:
    return "link_" + hashlib.sha256(f"{relation}|{old_document_id}|{new_document_id}|{method}".encode()).hexdigest()[:20]


class LinkStore:
    """Document-to-document links with their quoted evidence and trust decision."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def all(self) -> list[DocumentLink]:
        if not self.path.exists():
            return []
        return [DocumentLink.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))["links"]]

    def get(self, link_id: str) -> DocumentLink | None:
        return next((item for item in self.all() if item.link_id == link_id), None)

    def for_old(self, document_id: str) -> list[DocumentLink]:
        return [item for item in self.all() if item.old_document_id == document_id]

    def for_new(self, document_id: str) -> list[DocumentLink]:
        return [item for item in self.all() if item.new_document_id == document_id]

    def pending_review(self) -> list[DocumentLink]:
        return [item for item in self.all() if item.trust is LinkTrust.REVIEW_REQUIRED]

    def add_if_new(self, link: DocumentLink) -> tuple[DocumentLink, bool]:
        """Store a link once. Re-finding it later never resets a decision already made."""
        links = self.all()
        existing = next((item for item in links if item.link_id == link.link_id), None)
        if existing:
            return existing, False
        links.append(link)
        self._write(links)
        return link, True

    def replace(self, link: DocumentLink) -> None:
        self._write([link if item.link_id == link.link_id else item for item in self.all()])

    def _write(self, links: list[DocumentLink]) -> None:
        self.path.write_text(json.dumps({"links": [item.model_dump(mode="json") for item in links]}, indent=2), encoding="utf-8")
