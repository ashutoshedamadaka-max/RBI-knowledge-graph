import re

from app.models.graph import EntityType


_ALIASES = {
    "rbi": "reserve bank of india",
    "reserve bank": "reserve bank of india",
    "reserve bank of india": "reserve bank of india",
    "nbfcs": "nbfc",
    "non banking financial companies": "nbfc",
    "non-banking financial companies": "nbfc",
}


def canonical_name(name: str, entity_type: EntityType) -> str:
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", name.lower())).strip()
    return _ALIASES.get(normalized, normalized)


def entity_id(name: str, entity_type: EntityType) -> str:
    return f"{entity_type.value.lower()}:{canonical_name(name, entity_type)}"

