# Phase 6: evaluation harness

## Delivered

- A source-aligned RBI lending evaluation dataset stratified by single-hop, two-hop, multi-hop, comparison, temporal/change, and out-of-scope questions.
- Expected route and authoritative source URL for each in-scope case.
- One command to compare vector-only retrieval with the routed system.
- Measured source-recall@k, citation validity, routing accuracy, latency, cost, and per-hop retrieval recall.

## Honest reporting rule

The harness exists before benchmark claims. It does **not** write results into the README automatically and no score is presented as representative until the expected RBI documents have been ingested. This prevents a test corpus with missing source material from being mistaken for a production evaluation.

## Run

For a reproducible, no-cost benchmark against the current curated RBI lending corpus:

`python scripts/run_evaluation.py --bootstrap-curated`

This creates an isolated local evaluation corpus and forces deterministic answer generation.
It does not call OpenAI or modify the deployed Supabase knowledge base.

Retrieval recall is calculated only for questions that should be answerable from the
curated corpus. Out-of-scope questions are reported separately as abstention accuracy,
so they cannot distort the retrieval result.

The command writes local output to `data/evaluation/latest-results.json`. This file is ignored because it reflects the particular ingested corpus and configuration.
