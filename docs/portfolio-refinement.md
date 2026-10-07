# Portfolio refinement — 7 October 2026

## Implemented

- Position the prototype for lending/compliance research. Show selected-corpus scope, independence from RBI and the need to verify generated answers.
- Distinguish lifecycle-eligible documents from total indexed documents. Warn when the latest successful source check is older than eight days (conservative display threshold allowing weekly sources); do not imply all-source freshness.
- Keep all four navigation destinations accessible on mobile. Preserve the existing navy/teal design rather than rebuild the visual identity.
- Put evidence beside the answer on desktop and below it on mobile. Collapse process details and loading-stage detail. Keep citation selection and keyboard tab switching.
- Group citations by document, preserving separate passage targets. Stop reporting extracted HTML page 1 as original PDF pagination.
- Remove unsupported topic headings with a conservative lexical guard; keep the underlying claim text unchanged. Request shorter plain-language summaries from the model without another model call.
- Exclude explicit HTML deletion markup (`s`, `strike`, `del`, inline line-through) during extraction. Rebuild affected saved-HTML indexes with rollback protection while preserving lifecycle approvals.
- Require explicit historical/change intent: a document year alone is not historical. Apply the same temporal eligibility to graph fallback and vector-only evaluation. Display the limitation of historical research.
- Only display answer graph edges backed by selected evidence. Record the retrieval method that actually supplied eligible passages.
- Group update history by source; distinguish stored detector/reviewer notes from verbatim RBI evidence. Do not claim operational impact has been verified.
- Do not skip explicitly curated source checks because a listing keyword heuristic fails.
- Publish a separate manifest-backed deterministic evaluation, preserving old questions, approvals and the old report. Show small sample sizes and unmeasured capabilities.
- Serve the canonical frontend from both the API root and Vercel build, eliminating divergent preview UIs. Update README positioning and remove placeholder metrics.

## Partial / deliberately not claimed

- Claim correctness: heading alignment and citation mapping are safeguards, not semantic/legal verification. No factual-accuracy percentage is published.
- Historical authority: prior material can be retrieved; exact as-of applicability and full consolidated amendments are not reconstructed.
- Meaningful change summaries: raw structured differences can exist, but business impact and before/after legal interpretation are not independently verified. The UI labels these as monitoring events.
- Benchmark relevance: unchanged legacy labels include non-current sources. The measured 5/25 source-retrieval result is retained, not dressed up as current-answer accuracy.
- Production latency: local deterministic timing is not live-model latency, cold-start delay or a performance guarantee.
- User research: intended users and jobs are explained, but interviews, adoption, task-time improvements and business outcomes are not invented.

## Verification

Run `python -m pytest -q`, `node --test tests/frontend-behavior.test.cjs`, and the Vercel build. Use `scripts/publish_evaluation.py` in an isolated data directory for the manifest-backed benchmark. Desktop/mobile browser QA uses that isolated corpus, not production. Production monitoring and source approvals are not changed by this work.

Changes remain local until explicitly published. A live deployment still needs a smoke test of an OpenAI-backed answer and monitoring freshness after deployment.
