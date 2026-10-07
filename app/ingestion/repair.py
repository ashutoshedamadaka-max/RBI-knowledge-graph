"""Offline repair of legacy notification extraction; never fetch a newer version."""

import json
import logging
import re
from urllib.parse import urlsplit

from app.graph.extraction import DeterministicEntityExtractor
from app.ingestion.chunking import chunk_pages
from app.ingestion.parser import parse_document

logger = logging.getLogger(__name__)
CHROME = re.compile(r"skip to main content|not pressed|search the website", re.I)


def repair_legacy_notifications(service) -> int:
    repaired = 0
    for document in service.manifest.all():
        url = urlsplit(document.source_url or "")
        is_rbi_notification = url.hostname in {"rbi.org.in", "www.rbi.org.in"} and url.path.lower().endswith("/notificationuser.aspx")
        if document.mime_type != "text/html" and not (document.mime_type == "text/plain" and is_rbi_notification):
            continue
        old_chunks = service.vector_store.get_by_document_id(document.document_id)
        raw = service.settings.raw_dir / f"{document.document_id}.aspx"
        has_deleted_markup = raw.exists() and bool(re.search(r"<(?:s|strike|del)\b|text-decoration(?:-line)?\s*:[^;]*line-through", raw.read_text(encoding="utf-8"), re.I))
        if not has_deleted_markup and not any(CHROME.search(chunk.text) for chunk in old_chunks):
            continue
        if any(data.get("source_document_id") == document.document_id and data.get("extraction_method") != "deterministic"
               for _, _, data in service.graph_service.store.graph.edges(data=True)):
            logger.warning("legacy_extraction_repair_skipped document_id=%s reason=custom_graph_requires_review", document.document_id)
            continue
        # Prefer the original captured bytes, never the live URL: that might now
        # contain a different regulation or withdrawal marker.
        processed = service.settings.processed_dir / f"{document.document_id}.json"
        if raw.exists():
            pages = parse_document(raw, document.mime_type).pages
        elif processed.exists():
            pages = [page["text"] for page in json.loads(processed.read_text())["pages"]]
        else:
            pages = []
            for number in sorted({chunk.page_number for chunk in old_chunks}):
                words = []
                for chunk in sorted((c for c in old_chunks if c.page_number == number), key=lambda c: c.chunk_index):
                    incoming = chunk.text.split()
                    overlap = service.settings.chunk_overlap if words else 0
                    if overlap and words[-overlap:] != incoming[:overlap]:
                        # Do not guess how legacy chunks were split.
                        words = []
                        break
                    words.extend(incoming[overlap:])
                pages.append(" ".join(words))
        cleaned = []
        for page in pages:
            if CHROME.search(page):
                identifier = re.search(r"\bRBI/(?:[A-Z]+/)?\d{4}-\d{2}/\d+\b", page)
                if not identifier:
                    break
                page = page[identifier.start():]
                # Known legacy footer; retain all notification clauses above it.
                page = re.split(r"\b(?:Back to Previous Page|Top of the Page|Search the Website)\b", page, maxsplit=1, flags=re.I)[0]
            if not page.strip() or CHROME.search(page):
                break
            cleaned.append(page)
        if len(cleaned) != len(pages) or not cleaned:
            logger.warning("legacy_extraction_repair_skipped document_id=%s reason=unverified_boundaries", document.document_id)
            continue
        chunks = chunk_pages(document, cleaned, service.settings.chunk_size, service.settings.chunk_overlap)
        if [chunk.model_dump() for chunk in chunks] == [chunk.model_dump() for chunk in old_chunks]:
            continue
        paths = [service.vector_store.path, service.graph_service.store.path]
        before = {path.name: json.loads(path.read_text()) for path in paths if path.exists()}
        backup = service.settings.runtime_dir / "extraction_repair_backup.json"
        if not backup.exists():
            backup.write_text(json.dumps(before, indent=2))
        try:
            service.vector_store.remove_document_ids({document.document_id})
            service.vector_store.upsert(chunks)
            service.graph_service.store.remove_document_ids({document.document_id})
            extractor = DeterministicEntityExtractor()
            for chunk in chunks:
                service.graph_service.store.add_extraction(chunk, extractor.extract(chunk), persist=False)
            service.graph_service.apply_document_lifecycle(document)
        except Exception:
            for path in paths:
                if path.name in before:
                    path.write_text(json.dumps(before[path.name], indent=2))
            service.graph_service.store.graph = service.graph_service.store._load()
            raise
        repaired += 1
        logger.info("legacy_extraction_repaired document_id=%s old_chunks=%s new_chunks=%s", document.document_id, len(old_chunks), len(chunks))
    return repaired
