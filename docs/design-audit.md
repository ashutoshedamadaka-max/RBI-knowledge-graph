# Product design audit and redesign

Audience: a recruiter or hiring manager discovering the product, followed by a researcher trying a lending-rule question. The interface should explain the problem quickly, demonstrate inspectable behavior, and make the engineering decisions and their evidence easy to find.

## The main findings

The previous home page required substantial reading before the live product. Navigation mixed product actions, technical explanations, and evaluation detail without a clear hierarchy. Several descriptions treated evidence coverage as stronger proof than the saved reports support. The graph appeared after a long explanation, and the automatic pipeline animation changed text before a visitor could finish reading it.

The redesign uses a persistent navigation rail on larger screens and an expandable navigation menu on phones. Product actions are grouped separately from the engineering story. Each page has a short introduction, a primary task, deeper detail on demand, and a useful next destination.

## Page-by-page changes

| Page | Visitor problem | Implemented changes |
| --- | --- | --- |
| Overview | Long headline and introductory text; live product buried below the story. | Short problem statement, source-history illustration, direct research action, saved-evidence results with limitations, and clear paths to use, explore, or read. |
| Ask a question | Narrow composer; empty panels; examples submitted immediately; sources relied on hover; answer reveal animation added delay. | Dedicated workspace, explicit submission, optional historical date, saved answer replay, real progress states, cancellation, recoverable errors, visible check labels, focused citation reading, and optional evidence graph. |
| How it works | Automatically changing dense text made reading difficult. | Interactive visual pipeline; manual selection and next/previous controls; optional play/pause; diagrams with brief explanations; measured evidence attached to relevant steps. |
| Build decisions | Long phase diary and several unsupported outcome or spending claims. | Decisions organized around transferable engineering lessons; animated comparison bars; explicit trade-offs; architecture diagram; practical next validation work. |
| Results & limits | Dense dashboard; evidence coverage described as answer correctness; limitations dispersed. | Evidence-grid explanation, exact-count headlines, question-type views, progressive disclosure of retrieval/graph/replay detail, real failure cases, and prominent benchmark and checker limitations. |
| Source library | Very long unfiltered tables; public page dominated by admin controls; stale or misleading loading values. | Title search, lifecycle filter, pagination, expandable document evidence and full passages, honest loading/error states, evaluated-release fallback, and collapsed maintainer tools. |
| Explore the graph | Visual map buried below extensive explanation; difficult to orient and navigate. | Real WebGL 3D scene, document overview, topic starters, search, selected-neighborhood view, node inspector, relationship evidence, previous-node navigation, camera controls, 2D alternative, timeline, and equivalent document list. |

## Shared interaction and accessibility work

- Visited pages retain state during in-app navigation. Research results, graph exploration, source filters, and comparison choices survive a trip to another tab.
- The research response appears as it arrives. A pending or failed check is not presented as a completed verification.
- Citation buttons move focus to the original passage. Keyboard users can return from the selected passage with Escape.
- The graph has keyboard camera controls, search/list selection, a 2D alternative, and a text fallback if WebGL is unavailable. It renders on interaction rather than continuously spinning.
- Content animation is optional. The tour pauses when leaving its page or hiding the document; reduced-motion preferences suppress animation.
- Navigation, focus indicators, skip link, form labels, contrast, responsive tables, disabled states, and touch targets were reviewed.
- Fonts are packaged with the application. The graph implementation is loaded only when its page is first visited.

## Evidence and availability

The explanatory pages read a generated summary of committed evaluation reports. `scripts/build_web_evidence.mjs` reproduces that summary and the unedited saved-answer example.

Live graph and library requests have a bounded wait. If unavailable, the interface switches to a clearly labelled snapshot from `data/releases/corpus-v2.zip`. `scripts/build_web_snapshot.py` produces the public allowlisted document fields, passages, graph overview, graph records, and manifest. It reads no credentials, environment files, production database, or private runtime data. Embedding vectors are excluded.

Saved documents and graph evidence are browsing aids. They are not presented as current monitoring, and live questions are never silently replaced by saved responses. The saved example has its own explicit label and retains the original unchecked-claim status.

The graph's spacing and depth are visual layout choices. The year control filters publication availability and shows recorded expiration; it does not claim to recreate historical graph extraction. Obligations are inspected through relationship details rather than the overview canvas.

## Verification and artifacts

Browser audit scripts:

- `scripts/design-audit.mjs`: every page at desktop and phone widths, page overflow, screenshots, and automated accessibility checks. The default test intentionally makes the live browsing endpoints unavailable to verify the snapshot fallback.
- `scripts/design-interactions.mjs`: query submission, response rendering, source inspection, cross-page persistence, errors, cancellation, refusals, recorded answers, walkthrough controls, reduced motion, and mobile dark mode. Responses use a previously saved smoke-test fixture; no paid model calls are made.
- `scripts/design-graph-check.mjs`: real saved graph navigation, camera changes, timeline, source passages, narrow phone/tablet layouts, and dark graph/library views.

The scripts use Playwright and axe-core installed in the ignored `data/runtime/design-audit` tooling directory and the local Chrome executable. Start the Vite preview on `http://127.0.0.1:5174/`, then run them from the repository root. Local verification artifacts are written under `data/runtime/design-audit/`.

Completed verification:

- All seven pages passed desktop and phone automated accessibility checks, with no page overflow or browser exceptions: `data/runtime/design-audit/visual-audit.json`.
- All pages also fit narrow phone and tablet widths. Graph navigation, camera movement, timeline, source browsing, and dark graph/library accessibility passed: `data/runtime/design-audit/graph-audit.json`.
- Research submission, citation focus, retained results, error recovery, cancellation, refusals, saved examples, walkthrough controls, reduced motion, comparison controls, and mobile navigation passed. The remaining five pages passed dark-theme accessibility checks: `data/runtime/design-audit/interaction-audit.json`.
- The review caught and fixed a button transition that could resubmit after cancellation, and made long source passages keyboard-scrollable. Cancelled request callbacks cannot replace a newer result.
- TypeScript checking and the Vite production build passed. Vite reports a size warning for the separately loaded Three.js graph bundle; it is fetched when the graph page is first opened.

Useful screenshots include:

- `data/runtime/design-audit/home-1440.png`
- `data/runtime/design-audit/ask-390.png`
- `data/runtime/design-audit/how-1440.png`
- `data/runtime/design-audit/built-1440.png`
- `data/runtime/design-audit/evals-1440.png`
- `data/runtime/design-audit/sources-1440.png`
- `data/runtime/design-audit/graph-1440.png`

These are local preview captures. Automated accessibility checks and developer inspection do not replace research with recruiters, assistive-technology users, or domain experts. Live backend responsiveness could not be verified from this environment during the redesign. No new product-quality evaluation or user-impact measurement was performed.

## Release state

Changes are built and verified in the local workspace. Preview: `http://127.0.0.1:5174/`. They have not been pushed or deployed to Vercel. A production smoke check is still needed after publication, including a live streamed answer against Render.
