# Phase 3: constrained provenance graph

## Delivered

- Small, explicit ontology: 11 entity types and 11 relationship types.
- Validated Pydantic extraction contract.
- Deterministic alias resolution for RBI and common NBFC forms.
- NetworkX multi-directed graph persisted as JSON.
- Every edge stores source chunk ID, source document ID, confidence, and extraction method.

## Extraction modes

`EXTRACTION_PROVIDER=deterministic` is the safe, no-cost default. It only extracts high-confidence patterns and conservative requirement sentences.

`EXTRACTION_PROVIDER=openai` enables strict-schema extraction with the configured low-cost model. It validates returned JSON and rejects relationships whose provenance does not match the source chunk. In a production run, extraction requests must be cached by chunk hash before the provider is enabled.

## Known limitations

The deterministic extractor cannot discover nuanced regulatory relationships. LLM extraction may miss or misclassify entities, so the graph is evidence navigation—not a source of truth. Answer generation will always cite the originating chunk.

