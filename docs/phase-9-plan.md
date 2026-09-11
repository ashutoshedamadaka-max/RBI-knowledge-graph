# Phase 9: Regulatory Monitoring & Change Intelligence

## Integration plan

Phase 9 reuses the existing ingestion service for processing newly discovered documents, the local vector store for incremental chunk upserts, the provenance graph for evidence-preserving links, citation validation for reports, the cost tracker for optional interpretation cost, and the existing API/dashboard surface.

The new monitoring layer owns only source discovery, run history, document lineage, deterministic comparisons, change reports, and alert de-duplication. It does not replace ingestion or retrieval.

## Local schema migration

- Document metadata: lifecycle, version number, validity interval, and current-version flag.
- Chunk metadata: validity interval, version number, and current-version flag.
- data/runtime/monitoring.json: source checks, immutable document-version lineage, regulatory updates, and sent alert IDs.

The future PostgreSQL migration maps these directly to source checks, document versions, regulatory updates, and alerts with indexes on canonical URL, content hash, current version, and detected time.
