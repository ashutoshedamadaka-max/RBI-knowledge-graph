# Phase 2: chunking and vector retrieval

## Delivered

- Page-bounded chunks, split on word boundaries with configurable overlap.
- Stable `chunk_id` values derived from document ID, page, ordinal, and text hash.
- A local, deterministic vector baseline with configurable top-k retrieval.
- Same chunk metadata contract for retrieval, later graph edges, citations, evaluation, and debugging.

## Storage strategy

The Docker deployment already provisions PostgreSQL with pgvector. The running development mode intentionally uses a filesystem vector index so Phase 2 can be exercised without a running database or an embedding-model download. The retrieval contract is isolated in `VectorRetrievalService`; Phase 3 replaces the store adapter with PostgreSQL/pgvector without changing callers.

## Quality limitation

The current dependency-free hashing embedder measures lexical similarity. It is a valid reproducible baseline, but not semantic retrieval. A sentence-transformer adapter and pgvector persistence are explicitly tracked as the next storage upgrade before benchmark reporting.

