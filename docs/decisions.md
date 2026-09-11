# Architecture decisions

## ADR-001: Local manifest before persistent document repository

**Decision:** Phase 1 stores document metadata and parsed text in a version-ignored local data directory. Docker Compose provisions PostgreSQL with pgvector, but document persistence is not coupled to it yet.

**Why:** Ingestion, source provenance, stable IDs, hashing, parsing, and cache behavior can be tested without database migrations or embedding infrastructure. This keeps the first runnable slice inexpensive and makes failures inspectable.

**Trade-off:** The filesystem manifest is not suitable for concurrent production workers. Phase 2 moves document/chunk metadata to PostgreSQL alongside pgvector.

## ADR-002: Content-addressed document identities

**Decision:** `document_id` is derived from a SHA-256 content hash (`doc_<first 16 hex>`). The full hash is preserved in metadata.

**Why:** Re-ingesting identical bytes is deterministic and does not repeat parsing or later LLM extraction.

**Trade-off:** A source URL can change while retaining the same content. Source URLs are preserved as provenance but are not identity.

## ADR-003: Start with NetworkX, keep graph behind a retrieval boundary

**Decision:** The initial graph implementation will use NetworkX and expose fixed retrieval functions rather than graph query strings.

**Why:** It demonstrates provenance-aware multi-hop retrieval without introducing a graph database before scale warrants it.

**Trade-off:** NetworkX is single-process and not a multi-user graph store. A Neo4j adapter can replace it later without changing route selection or answer generation contracts.

