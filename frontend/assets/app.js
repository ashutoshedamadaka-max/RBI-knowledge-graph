const base = String(window.RBI_API_BASE_URL || '').replace(/\/+$/, '');
const api = (path) => base + path;
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));

let lastQuery = '';
let latestDocuments = [];
let latestAnswer = null;
let loadingStartedAt = 0;
let loadingTimer = null;
let regulatoryUpdates = [];
let latestMonitoringStatus = null;
let evaluationReportLoaded = false;
let researchIsLoading = false;

const PRODUCT_VIEWS = new Set(['research', 'updates', 'how-it-works', 'evals']);
const viewElement = (view) => ({
  updates: '#updates-view',
  'how-it-works': '#how-it-works-view',
  evals: '#evals-view',
}[view]);

function routeView() {
  const candidate = window.location.hash.replace(/^#/, '');
  return PRODUCT_VIEWS.has(candidate) ? candidate : 'research';
}

function setActiveView(view) {
  $$('.nav-item').forEach((item) => {
    const active = item.dataset.productView === view;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
}
function showView(view, { focus = false } = {}) {
  const selected = PRODUCT_VIEWS.has(view) ? view : 'research';
  ['updates-view', 'how-it-works-view', 'evals-view'].forEach((id) => $(`#${id}`).classList.add('hidden'));
  const research = selected === 'research';
  $('#research').classList.toggle('hidden', !research);
  $('#knowledge-status').classList.toggle('hidden', !research);
  $('#analysis-state').classList.toggle('hidden', !research || !researchIsLoading);
  $('#result').classList.toggle('hidden', !research || !latestAnswer);
  $('#about').classList.toggle('hidden', !research);
  const target = viewElement(selected);
  if (target) $(target).classList.remove('hidden');
  setActiveView(selected);
  if (selected === 'updates') loadUpdatesView();
  if (selected === 'evals') loadEvaluationReport();
  if (selected === 'how-it-works') renderLifecycleLiveSummary(latestMonitoringStatus);
  window.requestAnimationFrame(() => revealPortfolioContent(selected));
  if (focus) {
    const focusTarget = target ? $(target) : $('#research');
    window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    focusTarget?.focus({ preventScroll: true });
  }
}

function navigateTo(view, { replace = false, focus = true } = {}) {
  const selected = PRODUCT_VIEWS.has(view) ? view : 'research';
  const hash = `#${selected}`;
  if (window.location.hash !== hash) {
    window.history[replace ? 'replaceState' : 'pushState']({ view: selected }, '', hash);
  }
  showView(selected, { focus });
}

function updateUnreadBadge(updates) {
  regulatoryUpdates = updates;
  const seenAt = new Date(localStorage.getItem('rbi-updates-last-seen-at') || 0).getTime();
  const unread = updates.filter((update) => new Date(update.detected_at).getTime() > seenAt).length;
  const badge = $('#update-badge');
  badge.textContent = unread > 99 ? '99+' : String(unread);
  badge.classList.toggle('hidden', unread === 0);
  badge.setAttribute('aria-label', `${unread} unread regulatory update${unread === 1 ? '' : 's'}`);
}

function markUpdatesSeen() {
  const newest = regulatoryUpdates.reduce((latest, update) => Math.max(latest, new Date(update.detected_at).getTime()), 0);
  if (newest) localStorage.setItem('rbi-updates-last-seen-at', new Date(newest).toISOString());
  updateUnreadBadge(regulatoryUpdates);
}

function relativeTime(value) {
  if (!value) return 'No successful check recorded';
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return 'Checked just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `Checked ${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `Checked ${hours} hr ago`;
  return `Checked ${Math.round(hours / 24)} days ago`;
}

function formatDateTime(value) {
  if (!value || Number.isNaN(new Date(value).getTime())) return 'Not recorded';
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

function readableStatus(value) {
  return String(value || 'REVIEW_REQUIRED').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function updateLabel(update) {
  if (update.change_type === 'LIFECYCLE_CHANGED') return 'Status changed';
  return readableStatus(update.change_type);
}

function updateAction(update) {
  if (update.action_required) return 'Review required before this source can support current guidance.';
  if (['WITHDRAWN', 'REPEALED', 'SUPERSEDED'].includes(update.current_lifecycle)) return 'Excluded from current-guidance retrieval; retained for historical research.';
  return 'No user action is required. Current status is recorded in the knowledge base.';
}

function renderLifecycleLiveSummary(status) {
  const target = $('#lifecycle-live-summary');
  if (!target) return;
  if (!status) { target.textContent = 'Live monitoring status is temporarily unavailable.'; return; }
  const lifecycle = status.lifecycle_counts || {};
  const nonCurrent = (lifecycle.WITHDRAWN || 0) + (lifecycle.REPEALED || 0) + (lifecycle.SUPERSEDED || 0);
  const review = (lifecycle.REVIEW_REQUIRED || 0) + (lifecycle.UNKNOWN || 0);
  target.innerHTML = `<strong>Current monitored state</strong><span>${escapeHtml(String(status.document_count || 0))} indexed documents</span><span>${escapeHtml(String(status.tracked_source_count || 0))} official sources</span><span>${escapeHtml(String(nonCurrent))} non-current</span><span>${escapeHtml(String(review))} need review</span>`;
}

async function loadUpdatesView() {
  const list = $('#updates-list');
  if (!list) return;
  list.innerHTML = '<p class="relationship-empty">Loading monitored changes…</p>';
  try {
    const [updatesResponse, statusResponse] = await Promise.all([fetch(api('/regulatory-updates')), fetch(api('/monitoring-status'))]);
    if (!updatesResponse.ok || !statusResponse.ok) throw new Error();
    const updates = await updatesResponse.json();
    const status = await statusResponse.json();
    latestMonitoringStatus = status;
    const lifecycle = status.lifecycle_counts || {};
    const nonCurrent = (lifecycle.WITHDRAWN || 0) + (lifecycle.REPEALED || 0) + (lifecycle.SUPERSEDED || 0);
    const review = (lifecycle.REVIEW_REQUIRED || 0) + (lifecycle.UNKNOWN || 0);
    updateUnreadBadge(updates);
    markUpdatesSeen();
    $('#monitoring-health').textContent = relativeTime(status.last_checks?.[0]?.checked_at);
    $('#monitoring-summary').innerHTML = [
      ['Documents monitored', status.document_count], ['Official sources', status.tracked_source_count],
      ['Non-current sources', nonCurrent], ['Needs review', review], ['Last successful check', relativeTime(status.last_checks?.[0]?.checked_at)],
    ].map(([label, value]) => `<article><small>${escapeHtml(label)}</small><strong>${escapeHtml(String(value))}</strong></article>`).join('');
    list.innerHTML = updates.length ? updates.map((update) => {
      const lifecycle = update.current_lifecycle || 'REVIEW_REQUIRED';
      const evidence = update.status_evidence_excerpt ? `<blockquote>${escapeHtml(update.status_evidence_excerpt)}</blockquote>` : '';
      const statusSource = update.status_evidence_url && update.status_evidence_url !== update.source_url
        ? `<a href="${escapeHtml(update.status_evidence_url)}" target="_blank" rel="noreferrer">View status evidence →</a>` : '';
      return `<article class="update-card"><header><div><p class="eyebrow">${escapeHtml(updateLabel(update))}</p><h3>${escapeHtml(update.title)}</h3></div><span class="lifecycle-pill lifecycle-${escapeHtml(lifecycle)}">${escapeHtml(readableStatus(lifecycle))}</span></header><dl><div><dt>What changed</dt><dd>${escapeHtml(update.summary || 'A monitoring change was detected.')}</dd></div><div><dt>Detected</dt><dd>${escapeHtml(formatDateTime(update.detected_at))}</dd></div><div><dt>Current status</dt><dd>${escapeHtml(readableStatus(lifecycle))}</dd></div><div><dt>Action</dt><dd>${escapeHtml(updateAction(update))}</dd></div></dl>${evidence ? `<div class="status-evidence"><p>Supporting RBI status evidence</p>${evidence}</div>` : ''}<footer>${update.source_url ? `<a href="${escapeHtml(update.source_url)}" target="_blank" rel="noreferrer">Open original RBI source →</a>` : ''}${statusSource}</footer></article>`;
    }).join('') : '<section class="updates-empty"><p class="eyebrow">No recent material changes</p><h3>The latest monitor check found no new or modified lending documents.</h3><p>Lifecycle status and source availability are still tracked separately.</p></section>';
    renderLifecycleLiveSummary(status);
  } catch {
    list.innerHTML = '<p class="relationship-empty">Regulatory updates are temporarily unavailable. Please retry after the next monitoring check.</p>';
  }
}

function portfolioGraphHtml(graph) {
  if (!graph?.edges?.length) return '<p class="relationship-empty">No query-relevant graph relationship was returned for this question.</p>';
  const nodes = graph.nodes || [];
  const center = { x: 170, y: 120 };
  const radius = Math.min(78, 28 + nodes.length * 5);
  const points = new Map(nodes.map((node, index) => {
    const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(nodes.length, 1));
    return [node.node_id, { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius, node }];
  }));
  const lines = graph.edges.map((edge) => { const a = points.get(edge.source_id); const b = points.get(edge.target_id); return a && b ? `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>` : ''; }).join('');
  const graphNodes = [...points.values()].map(({ x, y, node }) => `<g class="portfolio-graph-node" tabindex="0" role="button" data-portfolio-node="${escapeHtml(node.node_id)}" aria-label="Highlight ${escapeHtml(node.name)}"><circle cx="${x}" cy="${y}" r="27"/><text x="${x}" y="${y - 3}">${escapeHtml(node.name.slice(0, 17))}</text><text x="${x}" y="${y + 10}">${escapeHtml(node.entity_type)}</text></g>`).join('');
  return `<svg viewBox="0 0 340 240" role="img" aria-label="Live query-relevant regulatory graph">${lines}${graphNodes}</svg>`;
}

function bindPortfolioGraphInteractions() {
  $$('.portfolio-graph-node').forEach((node) => {
    const select = () => $$('.portfolio-graph-node').forEach((item) => item.classList.toggle('selected', item === node));
    node.addEventListener('click', select);
    node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
  });
}

async function loadGraphExample(question) {
  const status = $('#graph-example-status');
  const target = $('#portfolio-graph');
  status.textContent = 'Reading the current knowledge graph…';
  target.innerHTML = '';
  try {
    const response = await fetch(api(`/graph-snapshot?query=${encodeURIComponent(question)}`));
    const graph = await response.json();
    if (!response.ok) throw new Error(graph.detail || 'Graph evidence is unavailable.');
    target.innerHTML = portfolioGraphHtml(graph);
    status.textContent = graph.edges?.length ? `${graph.edges.length} real relationship${graph.edges.length === 1 ? '' : 's'} returned for this question.` : 'No query-relevant relationship was returned for this question.';
    bindPortfolioGraphInteractions();
  } catch (error) {
    status.textContent = error.message || 'Graph evidence is temporarily unavailable.';
  }
}

function revealPortfolioContent(view) {
  const root = viewElement(view);
  if (!root) return;
  $(`${root}`)?.querySelectorAll('.story-section, .portfolio-reveal, .regression-ending').forEach((element) => element.classList.add('is-visible'));
}

function titleCase(value) {
  return String(value || '').replaceAll('-', ' ').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function resultCard(label, passed, total, description, state = 'measured') {
  if (!total || state !== 'measured') {
    return `<article class="evaluation-result unavailable"><p class="eyebrow">${escapeHtml(label)}</p><h3>Not yet evaluated</h3><p>${escapeHtml(description)}</p></article>`;
  }
  const percentage = Math.round((passed / total) * 100);
  return `<article class="evaluation-result"><p class="eyebrow">${escapeHtml(label)}</p><strong>${escapeHtml(String(passed))} <small>/ ${escapeHtml(String(total))}</small></strong><div class="result-bar" aria-label="${escapeHtml(label)}: ${escapeHtml(String(passed))} of ${escapeHtml(String(total))}"><i style="--result-width:${percentage}%"></i></div><p>${escapeHtml(description)}</p></article>`;
}

function renderEvaluationUnavailable(reason) {
  $('#evaluation-dataset-note').textContent = reason || 'A published benchmark run is not available yet.';
  $('#evaluation-categories').innerHTML = '<p class="relationship-empty">The evaluation harness and labelled datasets are implemented. Results appear here only after a reproducible run is published.</p>';
  $('#evaluation-results').innerHTML = [
    resultCard('Source retrieval', 0, 0, 'No published benchmark result is available.'),
    resultCard('Lifecycle safety', 0, 0, 'Automated regression coverage exists, but no benchmark score is published.'),
    resultCard('Citation traceability', 0, 0, 'No published benchmark result is available.'),
    resultCard('Abstention', 0, 0, 'No published benchmark result is available.'),
  ].join('');
  $('#evaluation-cases').innerHTML = '<p class="relationship-empty">Individual cases will appear with the published benchmark report.</p>';
}

function renderEvaluationReport(report) {
  const cases = Array.isArray(report.results) ? report.results : [];
  if (!cases.length || !report.generated_at) {
    renderEvaluationUnavailable('The available report does not contain the provenance required for portfolio display.');
    return;
  }
  const groups = cases.reduce((accumulator, item) => {
    const category = item.category || 'unlabelled';
    accumulator[category] = (accumulator[category] || 0) + 1;
    return accumulator;
  }, {});
  $('#evaluation-dataset-note').textContent = `${report.total_cases} labelled RBI lending questions · deterministic run · published ${formatDateTime(report.generated_at)}. This run exposes a legacy-source alignment gap, so it is shown as a re-baselining finding—not a generic answer-accuracy score.`;
  $('#evaluation-categories').innerHTML = Object.entries(groups).map(([category, count]) => `<article><strong>${escapeHtml(String(count))}</strong><span>${escapeHtml(titleCase(category))}</span></article>`).join('');
  $('#evaluation-results').innerHTML = [
    resultCard('Source retrieval', report.source_retrieval_pass_count, report.source_retrieval_evaluable_count, 'Did the labelled official RBI source appear in the eligible evidence set?'),
    resultCard('Lifecycle safety', 0, 0, 'Automated lifecycle regression tests exist; this benchmark does not yet publish a lifecycle-safety score.'),
    resultCard('Citation traceability', report.citation_traceability_pass_count, report.citation_traceability_evaluable_count, 'Did citation identifiers resolve to evidence returned by the same research turn?'),
    resultCard('Abstention', report.abstention_pass_count, report.abstention_evaluable_count, 'Did out-of-scope questions return no RBI research evidence?'),
  ].join('');
  $('#evaluation-cases').innerHTML = cases.map((item) => {
    const result = item.passed ? 'Pass' : 'Needs investigation';
    const sources = item.expected_source_urls?.length ? `<p><b>Expected source</b>${escapeHtml(item.expected_source_urls.join(' · '))}</p>` : '';
    const actual = item.actual_source_urls?.length ? `<p><b>Actual source</b>${escapeHtml(item.actual_source_urls.join(' · '))}</p>` : '';
    return `<details class="evaluation-case"><summary><span><b>${escapeHtml(item.case_id)}</b><small>${escapeHtml(titleCase(item.category))}</small></span><i class="case-${item.passed ? 'pass' : 'review'}">${result}</i></summary><div><p><b>Question</b>${escapeHtml(item.question)}</p><p><b>Expected behaviour</b>${escapeHtml(item.expected_behavior)}</p><p><b>Actual behaviour</b>${escapeHtml(item.actual_behavior)}</p>${sources}${actual}<p><b>Why this matters</b>${escapeHtml(item.why_this_matters)}</p></div></details>`;
  }).join('');
}

async function loadEvaluationReport() {
  if (evaluationReportLoaded) return;
  evaluationReportLoaded = true;
  try {
    const response = await fetch(api('/evaluation-report'));
    const payload = await response.json();
    if (!response.ok || !payload.available) {
      renderEvaluationUnavailable(payload.reason || 'No published benchmark report is available yet.');
      return;
    }
    renderEvaluationReport(payload.report);
  } catch {
    renderEvaluationUnavailable('The published benchmark report is temporarily unavailable.');
  }
}

function cleanTerms(value) {
  const ignored = new Set(['about','and','are','can','does','for','from','how','must','of','on','or','rbi','the','to','under','what','when','which','with','required','requirement']);
  return new Set((String(value || '').toLowerCase().match(/[a-z0-9]{3,}/g) || []).filter((term) => !ignored.has(term)));
}

function contextualTitle(research, query) {
  if (research?.display_title) return research.display_title;
  const normalized = String(query || '').toLowerCase();
  if (normalized.includes('digital lending') && normalized.includes('consent')) return 'Digital lending consent requirements';
  if (normalized.includes('penal charge')) return 'Penal charges in loan accounts';
  if (normalized.includes('property document')) return 'Release of property documents';
  if (normalized.includes('floating interest')) return 'Floating-rate loan disclosures';
  return 'RBI lending guidance';
}

function fallbackClaimTitle(text) {
  const normalized = String(text || '').toLowerCase();
  if (normalized.includes('camera') || normalized.includes('microphone') || normalized.includes('location')) return 'Device permissions require explicit consent';
  if (normalized.includes('give or deny consent') || normalized.includes('revoke consent')) return 'Borrowers control their data consent';
  if (normalized.includes('prior and explicit consent')) return 'Prior, explicit consent is required';
  if (normalized.includes('penal charge')) return 'Penal charges must be clearly disclosed';
  if (normalized.includes('property document')) return 'Property documents must be released on time';
  return 'Supporting RBI provision';
}

function showResearchMode(query) {
  $('#app-shell').classList.add('research-mode');
  $('#question').value = query;
  $('#new-research').classList.remove('hidden');
  $('#updates-view').classList.add('hidden');
  $('#updates-toggle').setAttribute('aria-expanded', 'false');
}

function citationMap(data) { return new Map((data.citations || []).map((citation, index) => [citation.chunk_id, index])); }
function citationButton(id, index) { return `<button class="citation-button" type="button" data-citation="${escapeHtml(id)}" aria-label="View source ${index + 1}">[${index + 1}]</button>`; }

function claimHtml(claim, index, sourceIndexes) {
  const citations = (claim.citation_ids || []).map((id) => citationButton(id, sourceIndexes.get(id) ?? index)).join('');
  const title = claim.title || fallbackClaimTitle(claim.text);
  return `<article class="claim"><span class="claim-number">${String(index + 1).padStart(2, '0')}</span><div><h4>${escapeHtml(title)}</h4><p>${escapeHtml(claim.text)}${citations}</p></div></article>`;
}

function claimsByCitation(research) {
  const claims = [research?.direct_answer, ...(research?.sections || []).flatMap((section) => section.claims || [])].filter(Boolean);
  const mapped = new Map();
  claims.forEach((claim) => (claim.citation_ids || []).forEach((id) => mapped.set(id, [...(mapped.get(id) || []), claim.text])));
  return mapped;
}

function evidenceExcerpt(chunk, claimTexts = []) {
  if (!chunk?.text) return 'Relevant passage unavailable.';
  const terms = cleanTerms(claimTexts.join(' '));
  const sentences = chunk.text.replace(/\s+/g, ' ').match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [chunk.text];
  let best = sentences[0].trim(); let bestScore = -1;
  sentences.forEach((sentence) => {
    const score = [...terms].filter((term) => sentence.toLowerCase().includes(term)).length;
    if (sentence.trim().length > 35 && score > bestScore) { best = sentence.trim(); bestScore = score; }
  });
  return best.length > 420 ? `${best.slice(0, 417)}…` : best;
}

function sourceCard(citation, index, evidence, citedClaims) {
  const chunk = evidence.find((item) => item.chunk_id === citation.chunk_id);
  const excerpt = evidenceExcerpt(chunk, citedClaims.get(citation.chunk_id));
  const page = Number.isFinite(citation.page_number) ? `Page ${citation.page_number}` : '';
  const lifecycle = chunk?.lifecycle || 'UNKNOWN';
  return `<article class="source-card" id="source-${escapeHtml(citation.chunk_id)}" tabindex="-1"><header><span class="index">${index + 1}</span><div><p class="passage-label">${index === 0 ? 'Primary evidence' : 'Supporting evidence'} <span class="lifecycle-pill lifecycle-${escapeHtml(lifecycle)}">${escapeHtml(lifecycle.replaceAll('_', ' '))}</span></p><h3>${escapeHtml(citation.document_title)}</h3>${page ? `<small>${escapeHtml(page)}</small>` : ''}</div></header><p class="passage-label">Relevant passage</p><blockquote>${escapeHtml(excerpt)}</blockquote>${citation.source_url ? `<a href="${escapeHtml(citation.source_url)}" target="_blank" rel="noreferrer">View original RBI source →</a>` : ''}</article>`;
}

function selectSource(chunkId, focus = true) {
  $$('.source-card').forEach((item) => item.classList.toggle('selected', item.id === `source-${chunkId}`));
  $$('.citation-button').forEach((item) => item.classList.toggle('selected', item.dataset.citation === chunkId));
  const card = document.getElementById(`source-${chunkId}`);
  if (!card) return;
  if (focus) { card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); card.focus({ preventScroll: true }); }
}

function citationPreview(button, chunkId) {
  const popover = $('#citation-popover');
  const citation = (latestAnswer?.citations || []).find((item) => item.chunk_id === chunkId);
  const chunk = (latestAnswer?.retrieved_evidence || []).find((item) => item.chunk_id === chunkId);
  if (!citation || !chunk) return;
  popover.innerHTML = `<strong>${escapeHtml(citation.document_title)}</strong><p>${escapeHtml(evidenceExcerpt(chunk, claimsByCitation(latestAnswer.research).get(chunkId)))}</p><small>${Number.isFinite(citation.page_number) ? `Page ${citation.page_number} · ` : ''}Select to view evidence</small>`;
  const rect = button.getBoundingClientRect();
  popover.style.left = `${Math.min(window.innerWidth - popover.offsetWidth - 16, Math.max(16, rect.left))}px`;
  popover.style.top = `${Math.max(12, rect.top - 12)}px`;
  popover.classList.remove('hidden');
}

function hideCitationPreview() { $('#citation-popover').classList.add('hidden'); }

function bindCitationInteractions() {
  $$('.citation-button').forEach((button) => {
    const show = () => citationPreview(button, button.dataset.citation);
    button.addEventListener('mouseenter', show);
    button.addEventListener('focus', show);
    button.addEventListener('mouseleave', hideCitationPreview);
    button.addEventListener('blur', hideCitationPreview);
    button.addEventListener('click', () => { activateTab('sources'); selectSource(button.dataset.citation); });
  });
}

function graphHtml(graph, sourceIndexes) {
  if (!graph?.edges?.length) return '<p class="relationship-empty">No query-relevant regulatory relationships were retrieved for this question.</p>';
  const nodes = graph.nodes || []; const center = { x: 160, y: 106 }; const radius = Math.min(62, 22 + nodes.length * 4);
  const points = new Map(nodes.map((node, index) => {
    const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(nodes.length, 1));
    return [node.node_id, { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius, node }];
  }));
  const edgeLines = graph.edges.map((edge) => { const a = points.get(edge.source_id), b = points.get(edge.target_id); return a && b ? `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>` : ''; }).join('');
  const graphNodes = [...points.values()].map(({ x, y, node }) => `<g class="graph-node" data-graph-node="${escapeHtml(node.node_id)}" role="button" tabindex="0" aria-label="Explore ${escapeHtml(node.name)}"><circle cx="${x}" cy="${y}" r="24"/><text x="${x}" y="${y - 2}">${escapeHtml(node.name.slice(0, 16))}</text><text x="${x}" y="${y + 10}">${escapeHtml(node.entity_type)}</text></g>`).join('');
  const names = new Map(nodes.map((node) => [node.node_id, node.name]));
  const details = graph.edges.map((edge) => `<article class="relationship-edge" data-edge="${escapeHtml(edge.source_id)} ${escapeHtml(edge.target_id)}"><strong>${escapeHtml(names.get(edge.source_id) || edge.source_id)}</strong><span>${escapeHtml(edge.relationship_type.replaceAll('_', ' ').toLowerCase())} →</span><strong>${escapeHtml(names.get(edge.target_id) || edge.target_id)}</strong>${sourceIndexes.has(edge.source_chunk_id) ? citationButton(edge.source_chunk_id, sourceIndexes.get(edge.source_chunk_id)) : ''}</article>`).join('');
  return `<div class="graph-wrap"><svg class="relationship-graph" viewBox="0 0 320 212" role="img" aria-label="Query-relevant regulatory relationship graph">${edgeLines}${graphNodes}</svg><div class="graph-details">${details}</div></div>`;
}

function bindGraphInteractions() {
  $$('.graph-node').forEach((node) => {
    const select = () => { $$('.graph-node').forEach((item) => item.classList.toggle('selected', item === node)); $$('.relationship-edge').forEach((edge) => edge.classList.toggle('selected', edge.dataset.edge.includes(node.dataset.graphNode))); };
    node.addEventListener('click', select);
    node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
  });
}

function activateTab(name) {
  $$('.evidence-tabs button').forEach((button) => { const active = button.dataset.tab === name; button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active)); });
  $('#sources-tab').classList.toggle('hidden', name !== 'sources');
  $('#relationships-tab').classList.toggle('hidden', name !== 'relationships');
}

function renderAnswer(data) {
  latestAnswer = data;
  const research = data.research || {}; const citations = data.citations || []; const sourceIndexes = citationMap(data);
  const insufficient = research.status === 'insufficient_evidence'; const outOfScope = research.status === 'out_of_scope';
  $('#user-turn-question').textContent = lastQuery;
  $('#answer-title').textContent = insufficient ? 'Insufficient evidence' : outOfScope ? 'Outside the knowledge base' : contextualTitle(research, lastQuery);
  $('#evidence-badge').textContent = citations.length ? `Based on ${citations.length} RBI source${citations.length === 1 ? '' : 's'}` : outOfScope ? 'RBI lending scope' : 'No source evidence';
  const direct = research.direct_answer; let html = '';
  if (direct) html += `<section class="direct-answer"><h3>${outOfScope ? 'Knowledge-base boundary' : insufficient ? 'What we found' : 'In brief'}</h3><p>${escapeHtml(direct.text)}${(direct.citation_ids || []).map((id) => citationButton(id, sourceIndexes.get(id) ?? 0)).join('')}</p></section>`;
  (research.sections || []).forEach((section) => { if (section.claims?.length) html += `<section class="answer-section"><h3>${escapeHtml(section.title === 'Supporting provisions' ? 'Key requirements' : section.title)}</h3>${section.claims.map((claim, index) => claimHtml(claim, index, sourceIndexes)).join('')}</section>`; });
  if (!html) html = '<section class="direct-answer"><h3>Research result</h3><p>No structured answer was returned. Please retry the research request.</p></section>';
  $('#structured-answer').innerHTML = html;
  const claims = claimsByCitation(research);
  $('#sources-tab').innerHTML = citations.length ? citations.map((citation, index) => sourceCard(citation, index, data.retrieved_evidence || [], claims)).join('') : '<p class="relationship-empty">No citable RBI source was retrieved for this request.</p>';
  const graph = research.graph_context; $('#relationships-tab').innerHTML = graphHtml(graph, sourceIndexes);
  $('#source-tab-count').textContent = citations.length ? `(${citations.length})` : '';
  $('#graph-tab-count').textContent = graph?.edges?.length ? `(${graph.edges.length})` : '';
  const hasEvidence = Boolean(citations.length || graph?.edges?.length); $('#evidence-panel').classList.toggle('hidden', !hasEvidence);
  const related = research.related_questions || []; $('#related-questions').classList.toggle('hidden', !related.length); $('#related-question-list').innerHTML = related.map((item) => `<button type="button" data-follow-up="${escapeHtml(item)}">${escapeHtml(item)} →</button>`).join('');
  const trace = [citations.length ? `${citations.length} official source${citations.length === 1 ? '' : 's'} retrieved` : null, data.citation_valid ? 'Answer linked to source evidence' : null, graph?.edges?.length ? `${graph.edges.length} regulatory relationship${graph.edges.length === 1 ? '' : 's'} found` : null].filter(Boolean);
  $('#research-trace').innerHTML = trace.map((item) => `<span>✓ ${escapeHtml(item)}</span>`).join('');
  const route = String(data.route || 'RETRIEVAL').toLowerCase();
  $('#behind-route').textContent = `${route} retrieval`;
  const pipeline = data.pipeline || {};
  const validity = pipeline.historical_query ? 'Historical research keeps prior material available' : `${pipeline.excluded_after_validity_check || 0} candidate${pipeline.excluded_after_validity_check === 1 ? '' : 's'} excluded after validity check`;
  $('#behind-summary').innerHTML = `<dl>
    <div><dt>Question</dt><dd>RBI lending scope checked</dd></div>
    <div><dt>Relationships</dt><dd>${graph?.edges?.length ? `${graph.edges.length} relevant relationship${graph.edges.length === 1 ? '' : 's'} retrieved` : 'No query-relevant relationship retrieved'}</dd></div>
    <div><dt>Validity</dt><dd>${escapeHtml(validity)}</dd></div>
    <div><dt>Evidence</dt><dd>${pipeline.selected_evidence_count ?? citations.length} eligible passage${(pipeline.selected_evidence_count ?? citations.length) === 1 ? '' : 's'} selected</dd></div>
    <div><dt>Citations</dt><dd>${citations.length ? (data.citation_valid ? 'Mapped to retrieved evidence' : 'No verified citation mapping') : 'No citations for this response'}</dd></div>
  </dl><p class="behind-note">This summary uses artifacts returned by this research turn.</p>`;
  bindCitationInteractions(); bindGraphInteractions();
  $$('[data-follow-up]').forEach((button) => button.addEventListener('click', () => { $('#question').value = button.dataset.followUp; $('#query-form').requestSubmit(); }));
}

function setProgress(stage) {
  const stages = ['understanding_question','searching_regulatory_relationships','retrieving_official_evidence','checking_regulatory_validity','selecting_authoritative_evidence','building_grounded_answer']; const index = stages.indexOf(stage);
  $$('#research-progress li').forEach((item, itemIndex) => { item.classList.toggle('active', itemIndex === index); item.classList.toggle('complete', itemIndex < index); });
}

function setLoading(loading) {
  researchIsLoading = loading;
  $('#analysis-state').classList.toggle('hidden', !loading); $('#analysis-state').setAttribute('aria-busy', String(loading));
  if (loading) { $('#result').classList.add('hidden'); $('#behind-route').textContent = ''; $('#behind-summary').innerHTML = '<p>Research is preparing a new evidence-backed answer.</p>'; setProgress('understanding_question'); loadingStartedAt = Date.now(); clearInterval(loadingTimer); loadingTimer = setInterval(() => { $('#loading-time').textContent = `Researching · ${Math.max(1, Math.round((Date.now() - loadingStartedAt) / 1000))}s`; }, 1000); }
  else { clearInterval(loadingTimer); }
}

function showError(message) {
  $('#behind-route').textContent = '';
  $('#behind-summary').innerHTML = '<p>The research service did not return evidence for this turn.</p>';
  $('#research-error').innerHTML = `<h2>We couldn’t complete this research request.</h2><p>${escapeHtml(message)}</p><button id="retry-research" type="button">Try again</button>`;
  $('#research-error').classList.remove('hidden'); $('#retry-research').addEventListener('click', () => $('#query-form').requestSubmit());
}

async function requestResearch(query) {
  const response = await fetch(api('/query/stream'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) });
  if (!response.ok || !response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || 'The RBI research service is temporarily unavailable.'); }
    const fallback = await fetch(api('/query'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) });
    const data = await fallback.json(); if (!fallback.ok) throw new Error(data.detail || 'The RBI research service is temporarily unavailable.'); return data;
  }
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let result = null;
  while (true) {
    const { done, value } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n'); buffer = events.pop();
    events.forEach((event) => { const type = event.match(/^event:\s*(.+)$/m)?.[1]; const raw = event.match(/^data:\s*(.+)$/m)?.[1]; if (!type || !raw) return; const payload = JSON.parse(raw); if (type === 'progress') setProgress(payload.stage); else if (type === 'result') result = payload; else if (type === 'error') throw new Error(payload.detail); });
  }
  if (!result) throw new Error('The RBI research service did not return a result. Please retry.');
  return result;
}

async function loadStatus() {
  try {
    const [statusResponse, documentsResponse, updatesResponse] = await Promise.all([fetch(api('/monitoring-status')), fetch(api('/documents')), fetch(api('/regulatory-updates'))]);
    if (!statusResponse.ok || !documentsResponse.ok) throw new Error();
    const status = await statusResponse.json(); const documentList = await documentsResponse.json(); latestDocuments = documentList.documents || []; latestMonitoringStatus = status;
    if (updatesResponse.ok) updateUnreadBadge(await updatesResponse.json());
    const checks = status.last_checks || []; const latest = checks[0]?.checked_at;
    $('#document-count').textContent = `${status.document_count} RBI documents`; $('#source-count').textContent = `${status.tracked_source_count} official sources`;
    const topics = status.topics || []; $('#topic-labels').innerHTML = topics.slice(0, 4).map((topic) => `<span>${escapeHtml(topic)}</span>`).join(''); $('#topic-overflow').textContent = topics.length > 4 ? `+${topics.length - 4}` : ''; $('#topic-overflow').classList.toggle('hidden', topics.length <= 4);
    const lifecycle = status.lifecycle_counts || {}; const reviewCount = (lifecycle.REVIEW_REQUIRED || 0) + (lifecycle.UNKNOWN || 0); const withdrawnCount = (lifecycle.WITHDRAWN || 0) + (lifecycle.REPEALED || 0) + (lifecycle.SUPERSEDED || 0);
    $('#non-current-count').textContent = `${withdrawnCount} non-current`; $('#review-count').textContent = `${reviewCount} needs review`;
    $('#knowledge-summary').textContent = relativeTime(latest); $('#header-last-check').textContent = relativeTime(latest); $('#knowledge-health').textContent = reviewCount ? `${reviewCount} status review${reviewCount === 1 ? '' : 's'}` : status.health === 'healthy' ? '● Live' : 'Needs review'; $('#source-live').classList.toggle('healthy', status.health === 'healthy' && !reviewCount);
    if (withdrawnCount) $('#knowledge-health').textContent = `${withdrawnCount} non-current · ${reviewCount} review`;
    renderLifecycleLiveSummary(status);
  } catch {
    $('#document-count').textContent = 'Knowledge base unavailable'; $('#source-count').textContent = 'Status will retry on refresh'; $('#non-current-count').textContent = ''; $('#review-count').textContent = ''; $('#knowledge-health').textContent = 'Unavailable';
  }
}

$('#query-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const query = $('#question').value.trim(); if (!query) return;
  lastQuery = query; $('#user-turn-question').textContent = query; showResearchMode(query); $('#submit').disabled = true; setLoading(true); $('#research-error').classList.add('hidden');
  try { const data = await requestResearch(query); renderAnswer(data); $('#result').classList.remove('hidden'); }
  catch (error) { $('#result').classList.remove('hidden'); $('#evidence-panel').classList.add('hidden'); $('#workspace-grid').classList.add('answer-only'); showError(error.message); }
  finally { setLoading(false); $('#submit').disabled = false; }
});

$$('[data-question]').forEach((button) => button.addEventListener('click', () => { $('#question').value = button.dataset.question; $('#question').focus(); }));
$('#follow-up-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const question = $('#follow-up-question').value.trim();
  if (!question) return;
  $('#question').value = question;
  $('#follow-up-question').value = '';
  $('#query-form').requestSubmit();
});
$('#new-research').addEventListener('click', () => { $('#app-shell').classList.remove('research-mode'); $('#result').classList.add('hidden'); $('#analysis-state').classList.add('hidden'); $('#new-research').classList.add('hidden'); $('#question').value = ''; $('#question').focus(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
$$('.evidence-tabs button').forEach((button) => button.addEventListener('click', () => activateTab(button.dataset.tab)));
function openCatalog() { const dialog = $('#source-catalog'); $('#catalog-content').innerHTML = latestDocuments.length ? latestDocuments.map((document) => { const lifecycle = document.lifecycle || 'UNKNOWN'; const detail = document.status_evidence_excerpt ? `<p>${escapeHtml(document.status_evidence_excerpt)}</p>` : ''; const review = ['UNKNOWN', 'REVIEW_REQUIRED'].includes(lifecycle) ? `<button class="review-source" type="button" data-review-document="${escapeHtml(document.document_id)}">Review status</button>` : ''; return `<article class="catalog-card"><h3>${escapeHtml(document.title)} <span class="lifecycle-pill lifecycle-${escapeHtml(lifecycle)}">${escapeHtml(lifecycle.replaceAll('_', ' '))}</span></h3><p>${document.page_count ? `Pages ${escapeHtml(document.page_count)} · ` : ''}Indexed RBI material</p>${detail}${document.source_url ? `<a href="${escapeHtml(document.source_url)}" target="_blank" rel="noreferrer">Open original source →</a>` : ''}${review}</article>`; }).join('') : '<p class="relationship-empty">Document details are not available yet. Refresh after the knowledge base loads.</p>'; $$('[data-review-document]').forEach((button) => button.addEventListener('click', () => openReviewDialog(button.dataset.reviewDocument))); dialog.showModal(); }

function openReviewDialog(documentId) { const document = latestDocuments.find((item) => item.document_id === documentId); if (!document) return; $('#review-document-id').value = document.document_id; $('#review-document-title').textContent = document.title; $('#review-evidence-url').value = document.source_url || ''; $('#review-evidence-excerpt').value = ''; $('#review-admin-key').value = ''; $('#review-result').textContent = ''; $('#review-dialog').showModal(); }

$('#review-form').addEventListener('submit', async (event) => { event.preventDefault(); const documentId = $('#review-document-id').value; const key = $('#review-admin-key').value; const result = $('#review-result'); result.textContent = 'Recording approval…'; try { const response = await fetch(api(`/admin/documents/${encodeURIComponent(documentId)}/lifecycle-review`), { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Key': key }, body: JSON.stringify({ lifecycle: $('#review-lifecycle').value, evidence_url: $('#review-evidence-url').value, evidence_excerpt: $('#review-evidence-excerpt').value }) }); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.detail || 'Approval could not be recorded.'); result.textContent = 'Approved status recorded.'; $('#review-admin-key').value = ''; await loadStatus(); setTimeout(() => { $('#review-dialog').close(); if ($('#source-catalog').open) openCatalog(); }, 550); } catch (error) { result.textContent = error.message; } });
$$('[data-product-view]').forEach((button) => button.addEventListener('click', () => navigateTo(button.dataset.productView)));
$('#graph-example-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const question = $('#graph-example-question').value.trim();
  if (question) loadGraphExample(question);
});
window.addEventListener('popstate', () => showView(routeView(), { focus: true }));
window.addEventListener('hashchange', () => showView(routeView(), { focus: true }));
$('#view-all-sources').addEventListener('click', openCatalog); $('#close-source-catalog').addEventListener('click', () => $('#source-catalog').close());
$('#close-review-dialog').addEventListener('click', () => $('#review-dialog').close());
loadStatus();
navigateTo(routeView(), { replace: true, focus: false });
