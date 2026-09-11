# Architecture

```mermaid
flowchart TB
  sources[RBI authoritative sources] --> ingest[Document ingestion]
  ingest --> parsed[Page-preserving parsing]
  parsed --> chunks[Chunking + metadata + stable chunk ID]
  chunks --> vectors[Vector index]
  chunks --> extraction[Constrained entity/relationship extraction]
  extraction --> graph[Provenance knowledge graph]
  question[User question] --> router[Query router]
  router --> vectors
  router --> graph
  vectors --> merge[Evidence merger]
  graph --> merge
  merge --> generation[Grounded answer generation]
  generation --> validator[Citation validator]
  validator --> answer[Answer + sources + evidence view]

  evalset[36 labeled evaluation questions] --> baseline[Vector-only baseline]
  evalset --> proposed[Routed retrieval]
  baseline --> metrics[Hop-stratified metrics]
  proposed --> metrics
```

The graph and vector stores share the same content-addressed chunk identity. Graph edges therefore point to the exact source chunk available to citations, debugging, and evaluation.

