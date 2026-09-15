import hashlib
import html
import re
from abc import ABC, abstractmethod
from urllib.parse import urljoin

import httpx

from app.models.monitoring import DiscoveredDocument, RegulatorySource
from app.ingestion.parser import extract_html_text
from app.monitoring.lifecycle import LifecycleResolution, resolve_rbi_html_lifecycle


class SourceFetcher(ABC):
    @abstractmethod
    def discover(self, source: RegulatorySource) -> list[DiscoveredDocument]:
        raise NotImplementedError

    @abstractmethod
    def download_text(self, document: DiscoveredDocument) -> str:
        raise NotImplementedError

    def lifecycle_resolution(self, document: DiscoveredDocument) -> LifecycleResolution | None:
        return None


class RbiHttpFetcher(SourceFetcher):
    """Minimal RBI listing reader; exact parsers remain source-strategy specific."""

    def __init__(self) -> None:
        self._raw_pages: dict[str, str] = {}

    def discover(self, source: RegulatorySource) -> list[DiscoveredDocument]:
        if source.parser_strategy == "rbi_document":
            key = f"{source.url}|{source.source_name}"
            return [DiscoveredDocument(
                canonical_url=str(source.url),
                title=source.source_name,
                metadata_hash=hashlib.sha256(key.encode()).hexdigest(),
            )]
        response = httpx.get(str(source.url), follow_redirects=True, timeout=30)
        response.raise_for_status()
        matches = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', response.text, flags=re.I | re.S)
        discovered = []
        for href, label in matches:
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", label))).strip()
            url = urljoin(str(source.url), html.unescape(href))
            if title and ("notification" in url.lower() or "circular" in title.lower() or "lending" in title.lower()):
                key = f"{url}|{title}"
                discovered.append(DiscoveredDocument(canonical_url=url, title=title, metadata_hash=hashlib.sha256(key.encode()).hexdigest()))
        return list({item.canonical_url: item for item in discovered}.values())

    def download_text(self, document: DiscoveredDocument) -> str:
        response = httpx.get(document.canonical_url, follow_redirects=True, timeout=45)
        response.raise_for_status()
        self._raw_pages[document.canonical_url] = response.text
        return extract_html_text(response.text)

    def lifecycle_resolution(self, document: DiscoveredDocument) -> LifecycleResolution | None:
        raw = self._raw_pages.get(document.canonical_url)
        if raw is None:
            response = httpx.get(document.canonical_url, follow_redirects=True, timeout=45)
            response.raise_for_status()
            raw = response.text
            self._raw_pages[document.canonical_url] = raw
        return resolve_rbi_html_lifecycle(raw)
