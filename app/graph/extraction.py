import json
import os
import re
from abc import ABC, abstractmethod

import httpx

from app.config.settings import Settings
from app.models.chunks import ChunkMetadata
from app.models.graph import (
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
    RelationshipType,
)


class EntityExtractor(ABC):
    @abstractmethod
    def extract(self, chunk: ChunkMetadata) -> ExtractionResult:
        raise NotImplementedError


class DeterministicEntityExtractor(EntityExtractor):
    """Conservative, no-cost extractor used until an LLM is explicitly enabled."""

    entity_patterns = {
        "RBI": (EntityType.AUTHORITY, "Reserve Bank of India"),
        "Reserve Bank of India": (EntityType.AUTHORITY, "Reserve Bank of India"),
        "NBFC": (EntityType.REGULATED_ENTITY, "NBFC"),
        "bank": (EntityType.REGULATED_ENTITY, "Banks"),
        "regulated entities": (EntityType.REGULATED_ENTITY, "Regulated Entities"),
        "borrower": (EntityType.CUSTOMER, "Borrowers"),
        "customer": (EntityType.CUSTOMER, "Customers"),
        "digital lending": (EntityType.LENDING_PRODUCT, "Digital Lending"),
        "co-lending": (EntityType.LENDING_PRODUCT, "Co-lending"),
    }

    def extract(self, chunk: ChunkMetadata) -> ExtractionResult:
        entities = [
            ExtractedEntity(name=chunk.document_title, entity_type=EntityType.REGULATION),
        ]
        seen = {(chunk.document_title.lower(), EntityType.REGULATION)}
        for pattern, (entity_type, name) in self.entity_patterns.items():
            if re.search(rf"\b{re.escape(pattern)}\b", chunk.text, re.IGNORECASE):
                key = (name.lower(), entity_type)
                if key not in seen:
                    entities.append(ExtractedEntity(name=name, entity_type=entity_type, aliases=[pattern]))
                    seen.add(key)

        relationships: list[ExtractedRelationship] = []
        authority = next((item for item in entities if item.entity_type is EntityType.AUTHORITY), None)
        regulation = entities[0]
        if authority:
            relationships.append(self._edge(regulation, RelationshipType.ISSUED_BY, authority, chunk, 0.95))

        sentences = re.split(r"(?<=[.!?])\s+", chunk.text)
        for sentence in sentences:
            if re.search(r"\b(must|shall|requires|required to|is required to)\b", sentence, re.IGNORECASE):
                requirement = ExtractedEntity(name=sentence[:300].strip(), entity_type=EntityType.REQUIREMENT)
                entities.append(requirement)
                relationships.append(self._edge(regulation, RelationshipType.REQUIRES, requirement, chunk, 0.72))
                for entity in entities:
                    if entity.entity_type is EntityType.REGULATED_ENTITY:
                        relationships.append(self._edge(requirement, RelationshipType.APPLIES_TO, entity, chunk, 0.66))
        return ExtractionResult(entities=entities, relationships=relationships, provider="deterministic")

    @staticmethod
    def _edge(source: ExtractedEntity, kind: RelationshipType, target: ExtractedEntity, chunk: ChunkMetadata, confidence: float) -> ExtractedRelationship:
        return ExtractedRelationship(
            source_name=source.name,
            source_type=source.entity_type,
            relationship_type=kind,
            target_name=target.name,
            target_type=target.entity_type,
            confidence=confidence,
            chunk_id=chunk.chunk_id,
            source_document_id=chunk.document_id,
            extraction_method="deterministic",
        )


class OpenAIEntityExtractor(EntityExtractor):
    """Strict JSON extraction adapter; disabled unless explicitly configured."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def extract(self, chunk: ChunkMetadata) -> ExtractionResult:
        schema = ExtractionResult.model_json_schema()
        prompt = (
            "Extract only supported RBI lending-regulation entities and relationships. "
            "Do not infer facts absent from the chunk. Every relationship must use the supplied "
            f"chunk_id ({chunk.chunk_id}) and source_document_id ({chunk.document_id}).\n\n"
            f"DOCUMENT: {chunk.document_title}\nTEXT:\n{chunk.text}"
        )
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": "Return valid JSON only."}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "extraction", "strict": True, "schema": schema}},
                "temperature": 0,
            },
            timeout=45,
        )
        response.raise_for_status()
        payload = json.loads(response.json()["choices"][0]["message"]["content"])
        result = ExtractionResult.model_validate(payload)
        if any(edge.chunk_id != chunk.chunk_id or edge.source_document_id != chunk.document_id for edge in result.relationships):
            raise ValueError("Extraction returned invalid provenance.")
        return result


def get_extractor(settings: Settings) -> EntityExtractor:
    if settings.extraction_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EXTRACTION_PROVIDER=openai.")
        return OpenAIEntityExtractor(settings.openai_api_key, settings.openai_extraction_model)
    return DeterministicEntityExtractor()
