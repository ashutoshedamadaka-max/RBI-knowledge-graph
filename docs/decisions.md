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

## ADR-004: Deterministic hashing vectors for the first retrieval baseline

**Decision:** Phase 2 uses a local feature-hashing embedder, persisted beside the document manifest, behind a vector-retrieval service boundary.

**Why:** It creates a free, reproducible, testable retrieval baseline without a model download, GPU requirement, database migration, or API spend. It also makes the later Graph RAG comparison honest: vector-only metrics start from a known baseline.

**Trade-off:** Feature hashing captures lexical overlap rather than semantic similarity, so it is not the production-quality embedding choice. Before publishing benchmark claims, the adapter will be switched to sentence-transformer embeddings and pgvector persistence; the API and evidence contracts will remain unchanged.

## ADR-005: Template-only graph retrieval

**Decision:** The graph retriever exposes named traversal templates and a deterministic query router instead of accepting generated graph-query language.

**Why:** Regulatory questions need predictable behavior and evidence provenance. Templates make the allowed traversal scope reviewable, testable, and measurable by question type.

**Trade-off:** Coverage grows incrementally as new templates are designed. Unsupported relationship questions return limited evidence rather than an unbounded graph search.
