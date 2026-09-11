# Phase 5: grounded answers and citation validation

## Delivered

- `POST /query` orchestrates route selection, vector/graph evidence, generation, and validation.
- The default answer composer uses only retrieved chunk text and inserts machine-verifiable chunk citations.
- Optional OpenAI generation receives only the question plus retrieved evidence and is instructed to cite only supplied IDs.
- `validate_citations(answer, retrieved_chunks)` rejects any absent or invented chunk ID.
- Invalid model citations fail closed: the API returns a verification failure rather than an ungrounded answer.

## Remaining upgrade

Cost/token accounting is added in Phase 7. Until then, OpenAI generation is opt-in and responses report $0 only for the deterministic default.

