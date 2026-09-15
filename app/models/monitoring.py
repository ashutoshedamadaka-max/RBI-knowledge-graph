from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl

from app.models.documents import DocumentLifecycle


class SourceType(str, Enum):
    NOTIFICATIONS = "notifications"
    MASTER_DIRECTIONS = "master_directions"
    FAQ = "faq"
    PRESS_RELEASE = "press_release"
    DOCUMENT = "document"


class MonitoringRunStatus(str, Enum):
    NO_CHANGES = "NO_CHANGES"
    CHANGES_DETECTED = "CHANGES_DETECTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PARSING_FAILURE = "PARSING_FAILURE"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"


class DiscoveryStatus(str, Enum):
    NEW = "NEW"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"
    POSSIBLY_REMOVED = "POSSIBLY_REMOVED"


class Materiality(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RegulatorySource(BaseModel):
    source_id: str
    authority: str = "Reserve Bank of India"
    source_name: str
    url: HttpUrl
    source_type: SourceType
    regulatory_topics: list[str]
    enabled: bool = True
    polling_frequency: str = "daily"
    parser_strategy: str = "rbi_listing"
    approved_lifecycle: DocumentLifecycle | None = None
    approval_evidence_excerpt: str | None = None


class DiscoveredDocument(BaseModel):
    canonical_url: str
    title: str
    publication_date: datetime | None = None
    document_identifier: str | None = None
    metadata_hash: str


class DocumentVersion(BaseModel):
    version_id: str
    source_id: str
    canonical_url: str
    title: str
    document_identifier: str | None = None
    publication_date: datetime | None = None
    content_hash: str
    normalized_text_hash: str
    text_snapshot: str = ""
    document_id: str | None = None
    version: int
    lifecycle: DocumentLifecycle = DocumentLifecycle.ACTIVE
    is_current: bool = True
    valid_from: datetime
    valid_to: datetime | None = None


class SourceCheck(BaseModel):
    run_id: str
    source_id: str
    checked_at: datetime
    status: MonitoringRunStatus
    discovered_count: int = 0
    changes_detected: int = 0
    error: str | None = None


class StructuredDiff(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed_numbers: list[str] = Field(default_factory=list)
    changed_dates: list[str] = Field(default_factory=list)


class ChangeInterpretation(BaseModel):
    change_summary: str
    change_type: str
    affected_entities: list[str] = Field(default_factory=list)
    affected_requirements: list[str] = Field(default_factory=list)
    affected_products: list[str] = Field(default_factory=list)
    effective_date: datetime | None = None
    materiality: Materiality
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class RegulatoryUpdate(BaseModel):
    update_id: str
    source_id: str
    title: str
    publication_date: datetime | None = None
    detected_at: datetime
    change_type: DiscoveryStatus
    summary: str
    previous_version_id: str | None = None
    new_version_id: str
    materiality: Materiality = Materiality.LOW
    affected_entities: list[str] = Field(default_factory=list)
    affected_requirements: list[str] = Field(default_factory=list)
    affected_products: list[str] = Field(default_factory=list)
    affected_processes: list[str] = Field(default_factory=list)
    effective_date: datetime | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    source_url: str
    diff: StructuredDiff | None = None
    citation_valid: bool = False
    regulatory_fact: str = ""
    potential_operational_impact: str = ""
