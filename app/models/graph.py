from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    REGULATION = "Regulation"
    CIRCULAR = "Circular"
    MASTER_DIRECTION = "MasterDirection"
    REQUIREMENT = "Requirement"
    REGULATED_ENTITY = "RegulatedEntity"
    LENDING_PRODUCT = "LendingProduct"
    OBLIGATION = "Obligation"
    PROHIBITION = "Prohibition"
    CUSTOMER = "Customer"
    DATE = "Date"
    AUTHORITY = "Authority"


class RelationshipType(str, Enum):
    ISSUED_BY = "ISSUED_BY"
    APPLIES_TO = "APPLIES_TO"
    REQUIRES = "REQUIRES"
    PROHIBITS = "PROHIBITS"
    SUPERSEDES = "SUPERSEDES"
    AMENDS = "AMENDS"
    RELATED_TO = "RELATED_TO"
    EFFECTIVE_FROM = "EFFECTIVE_FROM"
    APPLIES_TO_PRODUCT = "APPLIES_TO_PRODUCT"
    REPLACES = "REPLACES"
    REFERENCES = "REFERENCES"


class ExtractedEntity(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)


class ExtractedRelationship(BaseModel):
    source_name: str
    source_type: EntityType
    relationship_type: RelationshipType
    target_name: str
    target_type: EntityType
    confidence: float = Field(ge=0, le=1)
    chunk_id: str
    source_document_id: str
    extraction_method: str


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    provider: str

