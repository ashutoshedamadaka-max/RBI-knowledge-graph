# Phase 7: observability and cost control

## Delivered

- Stable request IDs flow through `POST /query`.
- Each query emits a structured JSON log with route, methods, evidence IDs, graph counts, latency, model, cost, and citation result.
- Token/cost events are persisted locally and exposed through `GET /metrics`.
- Default deterministic mode records zero model calls and zero cost.
- OpenAI cost estimation uses configurable per-million-token rates and API-returned usage fields; it is an estimate, not a billing statement.

## Cost discipline

Document hashes prevent unchanged documents from being reprocessed. The OpenAI extraction and answer adapters are opt-in. The metrics endpoint is intentionally aggregate-only: raw prompts and retrieved evidence remain in application logs rather than user-facing telemetry.

