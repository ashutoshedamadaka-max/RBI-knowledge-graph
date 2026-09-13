import hashlib
import html
import re
from abc import ABC, abstractmethod
from urllib.parse import urljoin

import httpx

from app.models.monitoring import DiscoveredDocument, RegulatorySource


class SourceFetcher(ABC):
    @abstractmethod
    def discover(self, source: RegulatorySource) -> list[DiscoveredDocument]:
        raise NotImplementedError

    @abstractmethod
    def download_text(self, document: DiscoveredDocument) -> str:
        raise NotImplementedError


class RbiHttpFetcher(SourceFetcher):
    """Minimal RBI listing reader; exact parsers remain source-strategy specific."""

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
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(response.text))).strip()
