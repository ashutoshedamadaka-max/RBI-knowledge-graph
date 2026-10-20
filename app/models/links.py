from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class LinkRelation(str, Enum):
    SUPERSEDES = "SUPERSEDES"  # the new document replaces the old one
    AMENDS = "AMENDS"          # the new document changes the old one, which stays in force
    CANDIDATE = "CANDIDATE"    # a possible replacement with no explicit statement; never automatic


class LinkScope(str, Enum):
    WHOLE = "WHOLE"      # the whole old document is repealed or superseded
    PARTIAL = "PARTIAL"  # only named paragraphs, chapters or annexes


class LinkTrust(str, Enum):
    AUTO_TRUSTED = "AUTO_TRUSTED"        # explicit official evidence met every trust condition
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # suggested; waits for one-click approval
    APPROVED = "APPROVED"                # a reviewer confirmed it
    REJECTED = "REJECTED"                # a reviewer rejected it


class LinkProposal(BaseModel):
    """What a document's text says about another document, before it is matched to the corpus."""

    relation: LinkRelation
    scope: LinkScope
    method: str
    evidence_quote: str  # an exact substring of the document it was read from
    evidence_in: str = "new"  # "new": the successor says it; "old": the old page names its replacement
    target_references: list[str] = Field(default_factory=list)  # every normalised number printed for the other document
    target_date: date | None = None
    target_title: str | None = None


class DocumentLink(BaseModel):
    link_id: str
    relation: LinkRelation
    scope: LinkScope
    old_document_id: str
    new_document_id: str
    method: str
    evidence_quote: str
    evidence_url: str | None = None
    evidence_in: str = "new"
    trust: LinkTrust = LinkTrust.REVIEW_REQUIRED
    trust_reasons: list[str] = Field(default_factory=list)
    decided_by: str = "AUTOMATED"  # or ADMIN_REVIEW
    created_at: datetime
    decided_at: datetime | None = None
    reviewer_evidence_url: str | None = None
    reviewer_excerpt: str | None = None


class LinkReviewRequest(BaseModel):
    """A reviewer's confirmation of a suggested link, with the evidence they relied on."""

    evidence_url: HttpUrl
    evidence_excerpt: str = Field(min_length=20, max_length=1200)
