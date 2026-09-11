# Phase 4: query router and graph retrieval

## Delivered

- Transparent heuristic router: `VECTOR`, `GRAPH`, or `HYBRID`.
- Routing reasons are recorded in structured logs.
- Graph retrieval uses only five named templates:
  - regulation → requirements → applicable entities
  - regulation → superseded/replaced regulation
  - regulation → amendments
  - requirement → lending product
  - entity → applicable regulations
- Graph results return only evidence nodes, provenance-carrying edges, and source chunk IDs.

## Safety boundary

The system does not accept Cypher, Gremlin, or any model-generated graph query. Adding a new graph question type requires a reviewed template and a test.

## Router trade-off

The router is deliberately deterministic and cheap. It can make borderline mistakes, which the evaluation phase will measure with labeled route expectations before introducing a learned router.

