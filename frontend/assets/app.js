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
  const unread = groupUpdates(updates).filter((group) => new Date(group[0].detected_at).getTime() > seenAt).length;
  const badge = $('#update-badge');
  badge.textContent = unread > 99 ? '99+' : String(unread);
  badge.classList.toggle('hidden', unread === 0);
  badge.setAttribute('aria-label', `${unread} sources with unread monitoring events`);
}

function groupUpdates(updates) {
  const groups = new Map();
  [...updates].sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at)).forEach((update) => {
    const key = update.source_url || update.source_id || update.title;
    groups.set(key, [...(groups.get(key) || []), update]);
  });
  return [...groups.values()];
}

function monitoringFreshness(value, now = Date.now()) {
  const checked = new Date(value || '').getTime();
  if (!Number.isFinite(checked)) return { state: 'unavailable', label: 'Monitoring not verified' };
  // Some configured sources run weekly. This is a display-level freshness
  // threshold, not a claim that every source was successfully checked.
  if (now - checked > 8 * 86400000) return { state: 'stale', label: 'Monitoring overdue' };
  return { state: 'recent', label: 'Recent source check' };
}

function renderMonitoringFreshness(value, status = null) {
  const freshness = monitoringFreshness(value);
  if (freshness.state === 'recent' && status?.health === 'attention') {
    freshness.state = 'attention'; freshness.label = 'Some source checks failed';
  }
  const indicator = $('#source-live');
  indicator.classList.toggle('healthy', freshness.state === 'recent');
  indicator.dataset.freshness = freshness.state;
  $('#header-monitor-label').textContent = freshness.label;
  $('#header-last-check').textContent = relativeTime(value);
  $('#knowledge-health').textContent = freshness.label;
  $('#knowledge-summary').textContent = `${relativeTime(value)} · latest recorded check, not all-source verification`;
}

function latestSuccessfulCheck(status) {
  return (status.last_checks || []).find((check) => ['NO_CHANGES', 'CHANGES_DETECTED'].includes(check.status))?.checked_at;
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
  return 'Eligible under the recorded lifecycle status. This does not establish whether the change affects your business.';
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
    const latest = latestSuccessfulCheck(status);
    renderMonitoringFreshness(latest, status);
    $('#monitoring-health').textContent = `${monitoringFreshness(latest).label} · ${relativeTime(latest)}`;
    $('#monitoring-summary').innerHTML = [
      ['Documents monitored', status.document_count], ['Official sources', status.tracked_source_count],
      ['Non-current sources', nonCurrent], ['Needs review', review], ['Latest successful source check', relativeTime(latest)],
    ].map(([label, value]) => `<article><small>${escapeHtml(label)}</small><strong>${escapeHtml(String(value))}</strong></article>`).join('');
    list.innerHTML = updates.length ? groupUpdates(updates).map(([update, ...earlier]) => {
      const lifecycle = update.current_lifecycle || 'REVIEW_REQUIRED';
      const evidence = update.status_evidence_excerpt ? `<blockquote>${escapeHtml(update.status_evidence_excerpt)}</blockquote>` : '';
      const statusSource = update.status_evidence_url && update.status_evidence_url !== update.source_url
        ? `<a href="${escapeHtml(update.status_evidence_url)}" target="_blank" rel="noreferrer">View status evidence →</a>` : '';
      const history = earlier.length ? `<details class="event-history"><summary>${earlier.length} earlier monitoring event${earlier.length === 1 ? '' : 's'}</summary>${earlier.map((item) => `<p><b>${escapeHtml(formatDateTime(item.detected_at))} · ${escapeHtml(updateLabel(item))}</b><br>${escapeHtml(item.summary || 'No change summary recorded.')}</p>`).join('')}</details>` : '';
      return `<article class="update-card"><header><div><p class="eyebrow">${escapeHtml(updateLabel(update))}</p><h3>${escapeHtml(update.title)}</h3></div><span class="lifecycle-pill lifecycle-${escapeHtml(lifecycle)}">${escapeHtml(readableStatus(lifecycle))}</span></header><dl><div><dt>Recorded finding</dt><dd>${escapeHtml(update.summary || 'A monitoring change was detected.')} Regulatory impact has not been independently assessed here.</dd></div><div><dt>Detected</dt><dd>${escapeHtml(formatDateTime(update.detected_at))}</dd></div><div><dt>Status at this event</dt><dd>${escapeHtml(readableStatus(lifecycle))}</dd></div><div><dt>Knowledge-base handling</dt><dd>${escapeHtml(updateAction(update))}</dd></div></dl>${evidence ? `<details class="status-evidence"><summary>Recorded status note</summary><p>Stored detector or reviewer evidence; not necessarily a verbatim RBI quotation.</p>${evidence}</details>` : ''}<footer>${update.source_url ? `<a href="${escapeHtml(update.source_url)}" target="_blank" rel="noreferrer">Open original RBI source →</a>` : ''}${statusSource}</footer>${history}</article>`;
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
  const manifest = report.run_manifest;
  $('#evaluation-dataset-note').textContent = `${report.total_cases} labelled RBI lending questions · ${report.answer_provider || 'unspecified provider'} run · published ${formatDateTime(report.generated_at)}. ${manifest ? `Base commit ${manifest.git_commit?.slice(0, 8) || 'not recorded'}${manifest.working_tree_dirty ? ' + working changes (fingerprinted)' : ''} · ${manifest.corpus_document_count ?? 'unknown'} corpus documents · ${manifest.source_refresh_attempted ? 'source refresh attempted during run' : 'saved corpus snapshot; no refresh during run'}.` : 'Legacy report: no run manifest recorded.'} This measures the saved test corpus, not live-model accuracy or production response time. Historical labels are not rewritten to improve results.`;
  $('#evaluation-categories').innerHTML = Object.entries(groups).map(([category, count]) => `<article><strong>${escapeHtml(String(count))}</strong><span>${escapeHtml(titleCase(category))}</span></article>`).join('');
  $('#evaluation-results').innerHTML = [
    resultCard('Source retrieval', report.source_retrieval_pass_count, report.source_retrieval_evaluable_count, 'Did the labelled source appear? Legacy labels include non-current and unresolved documents: exclusion is not necessarily a retrieval-ranking error.'),
    resultCard('Lifecycle safety', 0, 0, 'Automated lifecycle regression tests exist; this benchmark does not yet publish a lifecycle-safety score.'),
    resultCard('Citation traceability', report.citation_traceability_pass_count, report.citation_traceability_evaluable_count, 'Did citation identifiers resolve to evidence returned by the same research turn?'),
    resultCard('Abstention', report.abstention_pass_count, report.abstention_evaluable_count, 'Did out-of-scope questions return no RBI research evidence?'),
  ].join('');
  $('#evaluation-results').innerHTML += `<p class="honesty-note">Routing: ${Math.round((report.routing_accuracy || 0) * cases.length)}/${cases.length} matched the labelled route. These are small samples, not reliability guarantees. Semantic claim correctness, live-model latency and user time savings are not scored by this run.</p>`;
  $('#evaluation-cases').innerHTML = cases.map((item) => {
    const result = item.passed ? 'Pass' : 'Needs investigation';
    const sources = item.expected_source_urls?.length ? `<p><b>Expected source</b>${escapeHtml(item.expected_source_urls.join(' · '))}</p>` : '';
    const actual = item.actual_source_urls?.length ? `<p><b>Actual source</b>${escapeHtml(item.actual_source_urls.join(' · '))}</p>` : '';
    return `<details class="evaluation-case"><summary><span><b>${escapeHtml(item.question)}</b><small>${escapeHtml(item.case_id)} · ${escapeHtml(titleCase(item.category))}</small></span><i class="case-${item.passed ? 'pass' : 'review'}">${result}</i></summary><div><p><b>Expected behaviour</b>${escapeHtml(item.expected_behavior)}</p><p><b>Actual behaviour</b>${escapeHtml(item.actual_behavior)}</p>${sources}${actual}<p><b>Why this matters</b>${escapeHtml(item.why_this_matters)}</p></div></details>`;
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
  if (normalized.includes('priority sector')) return 'Priority sector lending — source findings';
  return 'RBI lending guidance';
}

function showResearchMode(query) {
  $('#app-shell').classList.add('research-mode');
  $('#question').value = query;
  $('#new-research').classList.remove('hidden');
  $('#updates-view').classList.add('hidden');
  $('#updates-toggle').setAttribute('aria-expanded', 'false');
}

function sourceGroups(citations) {
  const groups = new Map();
  citations.forEach((citation) => {
    const key = citation.source_url || citation.document_id || citation.chunk_id;
    groups.set(key, [...(groups.get(key) || []), citation]);
  });
  return [...groups.values()];
}
function citationMap(data) { return new Map(sourceGroups(data.citations || []).flatMap((group, index) => group.map((citation) => [citation.chunk_id, index]))); }
function citationButton(id, index) { return `<button class="citation-button" type="button" data-citation="${escapeHtml(id)}" aria-label="View source ${index + 1}">[${index + 1}]</button>`; }

function claimHtml(claim, index, sourceIndexes) {
  const citations = (claim.citation_ids || []).map((id) => citationButton(id, sourceIndexes.get(id) ?? index)).join('');
  // Do not invent a new topic from a claim whose model heading was removed.
  return `<article class="claim"><span class="claim-number">${String(index + 1).padStart(2, '0')}</span><div>${claim.title ? `<h4>${escapeHtml(claim.title)}</h4>` : ''}<p>${escapeHtml(claim.text)}${citations}</p></div></article>`;
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

function sourceLocation(citation) {
  const url = String(citation.source_url || '');
  return /\.pdf(?:[?#]|$)/i.test(url) && Number.isFinite(citation.page_number) ? `PDF page ${citation.page_number}` : 'Web / text passage · original pagination not verified';
}

function sourceCard(citation, index, evidence, citedClaims) {
  const chunk = evidence.find((item) => item.chunk_id === citation.chunk_id);
  const excerpt = evidenceExcerpt(chunk, citedClaims.get(citation.chunk_id));
  const page = sourceLocation(citation);
  const lifecycle = chunk?.lifecycle || 'UNKNOWN';
  return `<article class="source-card" id="source-${escapeHtml(citation.chunk_id)}" tabindex="-1"><p class="passage-label">Passage <span class="lifecycle-pill lifecycle-${escapeHtml(lifecycle)}">${escapeHtml(lifecycle.replaceAll('_', ' '))}</span></p><small>${escapeHtml(page)}</small><blockquote>${escapeHtml(excerpt)}</blockquote>${chunk?.valid_from ? `<small>Stored validity start: ${escapeHtml(formatDateTime(chunk.valid_from))} (not necessarily RBI effective date)</small>` : ''}</article>`;
}

function selectSource(chunkId, focus = true) {
  $$('.source-card').forEach((item) => item.classList.toggle('selected', item.id === `source-${chunkId}`));
  $$('.citation-button').forEach((item) => item.classList.toggle('selected', item.dataset.citation === chunkId));
  const card = document.getElementById(`source-${chunkId}`);
  if (!card) return;
  if (focus) { card.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' }); card.focus({ preventScroll: true }); }
}

function citationPreview(button, chunkId) {
  const popover = $('#citation-popover');
  const citation = (latestAnswer?.citations || []).find((item) => item.chunk_id === chunkId);
  const chunk = (latestAnswer?.retrieved_evidence || []).find((item) => item.chunk_id === chunkId);
  if (!citation || !chunk) return;
  popover.innerHTML = `<strong>${escapeHtml(citation.document_title)}</strong><p>${escapeHtml(evidenceExcerpt(chunk, claimsByCitation(latestAnswer.research).get(chunkId)))}</p><small>${escapeHtml(sourceLocation(citation))} · Select to view evidence</small>`;
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
  $('#workspace-grid').classList.remove('answer-only');
  const research = data.research || {}; const citations = data.citations || []; const sourceIndexes = citationMap(data);
  const groups = sourceGroups(citations); const sourceCount = groups.length;
  const insufficient = research.status === 'insufficient_evidence'; const outOfScope = research.status === 'out_of_scope';
  $('#user-turn-question').textContent = lastQuery;
  $('#answer-title').textContent = insufficient ? 'Insufficient evidence' : outOfScope ? 'Outside the knowledge base' : contextualTitle(research, lastQuery);
  $('#evidence-badge').textContent = citations.length ? `${sourceCount} RBI document${sourceCount === 1 ? '' : 's'} · ${citations.length} cited passage${citations.length === 1 ? '' : 's'}` : outOfScope ? 'RBI lending scope' : 'No source evidence';
  const direct = research.direct_answer; let html = '';
  if (direct) html += `<section class="direct-answer"><h3>${outOfScope ? 'Knowledge-base boundary' : insufficient ? 'What we found' : data.pipeline?.answer_mode === 'excerpt' ? 'From retrieved RBI text' : 'In brief'}</h3><p>${escapeHtml(direct.text)}${(direct.citation_ids || []).map((id) => citationButton(id, sourceIndexes.get(id) ?? 0)).join('')}</p></section>`;
  let claimIndex = 0;
  (research.sections || []).forEach((section) => { if (section.claims?.length) html += `<section class="answer-section"><h3>${escapeHtml(section.title === 'Supporting provisions' ? 'Supporting details' : section.title)}</h3>${section.claims.map((claim) => claimHtml(claim, claimIndex++, sourceIndexes)).join('')}</section>`; });
  if (data.pipeline?.historical_query) html = `<p class="history-warning">Historical / change research: non-current sources may be included. This is not a verified reconstruction of rules in force on a specific date.</p>${html}`;
  if (insufficient) html += '<p class="answer-limit">This is a coverage limit, not a statement that RBI has no rule on this topic. Check the source catalogue or ask a narrower question.</p>';
  if (!insufficient && !outOfScope) html += `<p class="answer-limit">${data.pipeline?.answer_mode === 'excerpt' ? 'Source excerpts only; not a synthesized answer.' : 'AI-generated research summary.'} Citation links establish traceability, not legal correctness. Verify the original wording before acting.</p>`;
  if (!html) html = '<section class="direct-answer"><h3>Research result</h3><p>No structured answer was returned. Please retry the research request.</p></section>';
  $('#structured-answer').innerHTML = html;
  const claims = claimsByCitation(research);
  $('#sources-tab').innerHTML = citations.length ? groups.map((group, index) => `<section class="source-document"><header><span class="index">${index + 1}</span><h3>${escapeHtml(group[0].document_title)}</h3></header><small>${group.length} cited passage${group.length === 1 ? '' : 's'}</small>${group.map((citation) => sourceCard(citation, index, data.retrieved_evidence || [], claims)).join('')}${group[0].source_url ? `<a href="${escapeHtml(group[0].source_url)}" target="_blank" rel="noreferrer">Open original RBI document ↗</a>` : '<p>Original source link unavailable.</p>'}</section>`).join('') : '<p class="relationship-empty">No citable RBI source was retrieved for this request.</p>';
  const graph = research.graph_context; $('#relationships-tab').innerHTML = graphHtml(graph, sourceIndexes);
  $('#source-tab-count').textContent = sourceCount ? `(${sourceCount})` : '';
  $('#graph-tab-count').textContent = graph?.edges?.length ? `(${graph.edges.length})` : '';
  const hasEvidence = Boolean(citations.length || graph?.edges?.length); $('#evidence-panel').classList.toggle('hidden', !hasEvidence);
  const related = research.related_questions || []; $('#related-questions').classList.toggle('hidden', !related.length); $('#related-question-list').innerHTML = related.map((item) => `<button type="button" data-follow-up="${escapeHtml(item)}">${escapeHtml(item)} →</button>`).join('');
  const trace = [citations.length ? `${sourceCount} distinct RBI document${sourceCount === 1 ? '' : 's'}` : null, citations.length && data.citation_valid ? 'Answer linked to source evidence' : null, graph?.edges?.length ? `${graph.edges.length} regulatory relationship${graph.edges.length === 1 ? '' : 's'} found` : null].filter(Boolean);
  $('#research-trace').innerHTML = trace.map((item) => `<span>✓ ${escapeHtml(item)}</span>`).join('');
  const pipeline = data.pipeline || {};
  const method = pipeline.retrieval_method;
  $('#behind-route').textContent = ({vector:'Text retrieval', graph:'Graph-backed retrieval', hybrid:'Text + graph retrieval', none:'No eligible evidence'})[method] || 'Retrieval method not recorded';
  const validity = pipeline.historical_query ? 'Prior material permitted for historical/change research; no exact as-of reconstruction' : `Current-guidance filter applied; ${pipeline.excluded_after_validity_check || 0} additional merged candidates excluded`;
  $('#behind-summary').innerHTML = `<dl>
    <div><dt>Question</dt><dd>RBI lending scope checked</dd></div>
    <div><dt>Relationships</dt><dd>${graph?.edges?.length ? `${graph.edges.length} source-backed relationship${graph.edges.length === 1 ? '' : 's'} in selected evidence` : 'No eligible graph relationship shown; do not infer graph benefit'}</dd></div>
    <div><dt>Validity</dt><dd>${escapeHtml(validity)}</dd></div>
    <div><dt>Evidence</dt><dd>${pipeline.selected_evidence_count ?? citations.length} eligible passage${(pipeline.selected_evidence_count ?? citations.length) === 1 ? '' : 's'} selected</dd></div>
    <div><dt>Citations</dt><dd>${citations.length ? (data.citation_valid ? 'Mapped to retrieved evidence' : 'No verified citation mapping') : 'No citations for this response'}</dd></div>
    <div><dt>Response time</dt><dd>${Number.isFinite(data.latency_ms) ? `${(data.latency_ms / 1000).toFixed(1)}s server processing; network / wake-up time may add delay` : 'Not recorded'}</dd></div>
  </dl><p class="behind-note">This summary uses artifacts returned by this research turn.</p>`;
  bindCitationInteractions(); bindGraphInteractions();
  $$('[data-follow-up]').forEach((button) => button.addEventListener('click', () => { $('#question').value = button.dataset.followUp; $('#query-form').requestSubmit(); }));
}

function setProgress(stage) {
  const stages = ['understanding_question','searching_regulatory_relationships','retrieving_official_evidence','checking_regulatory_validity','selecting_authoritative_evidence','building_grounded_answer']; const index = stages.indexOf(stage);
  $$('#research-progress li').forEach((item, itemIndex) => { item.classList.toggle('active', itemIndex === index); item.classList.toggle('complete', itemIndex < index); });
  const entered = $$('#research-progress li')[index];
  if (entered) $('#loading-stage').textContent = entered.querySelector('strong').textContent;
}

function setLoading(loading) {
  researchIsLoading = loading;
  $('#analysis-state').classList.toggle('hidden', !loading); $('#analysis-state').setAttribute('aria-busy', String(loading));
  if (loading) { $('#result').classList.add('hidden'); $('#behind-route').textContent = ''; $('#behind-summary').innerHTML = '<p>Research is preparing a new evidence-backed answer.</p>'; setProgress('understanding_question'); loadingStartedAt = Date.now(); clearInterval(loadingTimer); loadingTimer = setInterval(() => { $('#loading-time').textContent = `Researching · ${Math.max(1, Math.round((Date.now() - loadingStartedAt) / 1000))}s`; }, 1000); }
  else { clearInterval(loadingTimer); }
}

function showError(message) {
  $('#structured-answer').innerHTML = '';
  $('#answer-title').textContent = 'Research unavailable';
  $('#evidence-badge').textContent = 'No answer returned';
  $('#research-trace').innerHTML = '';
  $('#related-questions').classList.add('hidden');
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
    const latest = latestSuccessfulCheck(status);
    const eligible = (status.lifecycle_counts?.ACTIVE || 0) + (status.lifecycle_counts?.AMENDED || 0);
    $('#document-count').textContent = `${eligible} eligible / ${status.document_count} indexed documents`; $('#source-count').textContent = `${status.tracked_source_count} selected sources monitored`;
    const topics = status.topics || []; $('#topic-labels').innerHTML = topics.slice(0, 4).map((topic) => `<span>${escapeHtml(topic)}</span>`).join(''); $('#topic-overflow').textContent = topics.length > 4 ? `+${topics.length - 4}` : ''; $('#topic-overflow').classList.toggle('hidden', topics.length <= 4);
    const lifecycle = status.lifecycle_counts || {}; const reviewCount = (lifecycle.REVIEW_REQUIRED || 0) + (lifecycle.UNKNOWN || 0); const withdrawnCount = (lifecycle.WITHDRAWN || 0) + (lifecycle.REPEALED || 0) + (lifecycle.SUPERSEDED || 0);
    $('#non-current-count').textContent = `${withdrawnCount} non-current`; $('#review-count').textContent = `${reviewCount} needs review`;
    renderMonitoringFreshness(latest, status);
    renderLifecycleLiveSummary(status);
  } catch {
    renderMonitoringFreshness(null);
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
$$('.evidence-tabs button').forEach((button, index, tabs) => button.addEventListener('keydown', (event) => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  activateTab(tabs[next].dataset.tab); tabs[next].focus();
}));
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
$('#evidence-slot').append($('#evidence-panel'));
loadStatus();
navigateTo(routeView(), { replace: true, focus: false });
