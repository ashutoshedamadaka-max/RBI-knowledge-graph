"""Evidence-first RBI lifecycle detection.

This detector deliberately makes only negative lifecycle findings that are
explicit in fetched RBI text. Everything else remains review-required: an
available URL or a recent date is not evidence of current authority.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from app.models.documents import DocumentLifecycle


@dataclass(frozen=True)
class LifecycleResolution:
    lifecycle: DocumentLifecycle
    excerpt: str
    checked_at: datetime


def resolve_lifecycle(text: str) -> LifecycleResolution:
    normalized = " ".join(text.split())
    checked_at = datetime.now(UTC)
    patterns = (
        (DocumentLifecycle.WITHDRAWN, r"(?:^|\n)\s*withdrawn\s*(?:$|\n)|\bwithdrawn\b\s*[.?!]?\s*$|\bthis (?:circular|master circular|direction|directions)\b.{0,80}\b(?:stands?|is) withdrawn\b"),
        (DocumentLifecycle.SUPERSEDED, r"\bthis (?:circular|master circular|direction|directions)\b.{0,80}\bsuperseded(?: by)?\b"),
        (DocumentLifecycle.REPEALED, r".{0,160}\bthis (?:circular|master circular|direction|directions)\b.{0,80}\b(?:stands?|is) repealed\b.{0,160}"),
    )
    for lifecycle, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return LifecycleResolution(lifecycle, match.group(0).strip(), checked_at)
    return LifecycleResolution(
        DocumentLifecycle.REVIEW_REQUIRED,
        "No explicit RBI lifecycle statement was detected automatically; current authority has not been established.",
        checked_at,
    )


def resolve_rbi_html_lifecycle(html: str) -> LifecycleResolution:
    """Read RBI's document-level status watermark, not navigation text."""
    checked_at = datetime.now(UTC)
    watermark = re.search(r"background\s*:\s*url\([^)]*withdrawn[^)]*\)", html, flags=re.IGNORECASE)
    if watermark:
        return LifecycleResolution(
            DocumentLifecycle.WITHDRAWN,
            "RBI marks this document with its official Withdrawn watermark.",
            checked_at,
        )
    return LifecycleResolution(
        DocumentLifecycle.REVIEW_REQUIRED,
        "No document-level RBI lifecycle watermark or explicit status statement was detected automatically.",
        checked_at,
    )
