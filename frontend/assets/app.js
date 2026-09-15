const apiBaseUrl = String(window.RBI_API_BASE_URL || '').replace(/\/+$/, '');
const apiUrl = (path) => apiBaseUrl + path;
const form = document.querySelector('#query-form');
const question = document.querySelector('#question');
const submit = document.querySelector('#submit');
const result = document.querySelector('#result');
const emptyState = document.querySelector('#empty-state');
const updatesView = document.querySelector('#updates-view');
const analysisState = document.querySelector('#analysis-state');
const knowledgeStatus = document.querySelector('#knowledge-status');
let analysisTimer;

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (character) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[character])); }
function formatCheckTime(checks) { return checks.length ? new Date(checks[0].checked_at).toLocaleString() : 'No check recorded yet'; }
function formatAnswer(value) {
  return escapeHtml(value).split(/\n\n+/).map((block) => {
    if (block.startsWith('### ')) return '<h3>' + block.slice(4) + '</h3>';
    const lines = block.split('\n');
    if (lines.every((line) => line.startsWith('- '))) return '<ul>' + lines.map((line) => '<li>' + line.slice(2) + '</li>').join('') + '</ul>';
    return '<p>' + lines.join('<br>') + '</p>';
  }).join('');
}
function sourceCard(citation, index) {
  const source = citation.source_url ? '<a href="' + escapeHtml(citation.source_url) + '" target="_blank" rel="noreferrer">Open source ↗</a>' : '';
  return '<article class="citation"><span class="citation-index">' + (index + 1) + '</span><div><h3>' + escapeHtml(citation.document_title) + '</h3><p>Page ' + citation.page_number + ' · ' + escapeHtml(citation.chunk_id) + '</p></div>' + source + '</article>';
}
function evidenceCard(item) { return '<article class="evidence-item"><strong>' + escapeHtml(item.document_title) + ' · page ' + item.page_number + '</strong><p>' + escapeHtml(item.text) + '</p></article>'; }
function setLoading(loading) {
  clearInterval(analysisTimer);
  analysisState.classList.toggle('hidden', !loading);
  if (!loading) return;
  const steps = [...document.querySelectorAll('.analysis-steps li')];
  let active = 0;
  const showStep = () => steps.forEach((step, index) => step.classList.toggle('active', index === active));
  showStep();
  analysisTimer = setInterval(() => { active = Math.min(active + 1, steps.length - 1); showStep(); }, 850);
}

async function loadKnowledgeStatus() {
  try {
    const response = await fetch(apiUrl('/monitoring-status'));
    if (!response.ok) throw new Error('Status is temporarily unavailable.');
    const status = await response.json(); const checks = status.last_checks || [];
    document.querySelector('#knowledge-status h2').textContent = status.document_count + ' RBI lending documents available';
    document.querySelector('#knowledge-summary').textContent = status.tracked_source_count + ' official RBI sources monitored · Last checked ' + formatCheckTime(checks);
    const health = document.querySelector('#knowledge-health');
    health.textContent = status.health === 'healthy' ? 'Monitoring healthy' : 'Needs review';
    health.classList.toggle('attention', status.health !== 'healthy');
  } catch (error) {
    knowledgeStatus.classList.add('status-unavailable');
    document.querySelector('#knowledge-status h2').textContent = 'Knowledge-base status unavailable';
    document.querySelector('#knowledge-summary').textContent = 'You can still ask a question while the status reconnects.';
    document.querySelector('#knowledge-health').textContent = 'Retrying';
  }
}

loadKnowledgeStatus();
document.querySelectorAll('[data-question]').forEach((button) => button.addEventListener('click', () => { question.value = button.dataset.question; question.focus(); }));
document.querySelector('#updates-toggle').addEventListener('click', async () => {
  updatesView.classList.toggle('hidden');
  document.querySelector('#updates-toggle span:last-child').textContent = updatesView.classList.contains('hidden') ? 'Regulatory updates' : 'Hide updates';
  if (updatesView.classList.contains('hidden')) return;
  try {
    const [updatesResponse, statusResponse] = await Promise.all([fetch(apiUrl('/regulatory-updates')), fetch(apiUrl('/monitoring-status'))]);
    if (!updatesResponse.ok || !statusResponse.ok) throw new Error('Regulatory updates are temporarily unavailable.');
    const updates = await updatesResponse.json(); const status = await statusResponse.json(); const checks = status.last_checks || [];
    document.querySelector('#monitoring-health').textContent = checks.length ? 'Last check ' + formatCheckTime(checks) : 'No check recorded';
    const changes = updates.length ? updates.map((update) => '<article class="citation"><span class="citation-index">' + escapeHtml(update.materiality[0]) + '</span><div><h3>' + escapeHtml(update.title) + '</h3><p>' + escapeHtml(update.change_type) + ' · ' + new Date(update.detected_at).toLocaleDateString() + '</p><p>' + escapeHtml(update.summary) + '</p></div><a href="' + escapeHtml(update.source_url) + '" target="_blank" rel="noreferrer">Open source ↗</a></article>').join('') : '<div class="updates-empty"><h3>No material updates detected</h3><p>The latest check found no new or revised RBI lending documents. Monitoring will continue on schedule.</p></div>';
    const sourceHealth = checks.length ? '<div class="monitor-summary">' + checks.map((check) => '<span class="source-check ' + (check.status === 'NO_CHANGES' ? 'healthy' : 'attention') + '">' + escapeHtml(check.source_id.replace(/^rbi_/, '').replaceAll('_', ' ')) + ' · ' + escapeHtml(check.status.replaceAll('_', ' ').toLowerCase()) + '</span>').join('') + '</div>' : '';
    document.querySelector('#updates-list').innerHTML = changes + sourceHealth;
  } catch (error) { document.querySelector('#updates-list').innerHTML = '<div class="updates-empty"><h3>Updates are temporarily unavailable</h3><p>' + escapeHtml(error.message) + '</p></div>'; }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault(); const value = question.value.trim(); if (!value) return;
  submit.disabled = true; submit.textContent = 'Analysing…'; setLoading(true); emptyState.classList.add('hidden'); result.classList.add('hidden');
  try {
    const response = await fetch(apiUrl('/query'), { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ query:value }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'The question could not be processed.');
    const outOfScope = data.in_scope === false; const routePill = document.querySelector('#route-pill');
    routePill.textContent = outOfScope ? 'OUTSIDE RBI LENDING SCOPE' : data.route + ' RETRIEVAL'; routePill.classList.toggle('out-of-scope', outOfScope);
    document.querySelector('#result-label').textContent = outOfScope ? 'Knowledge-base boundary' : 'Grounded response';
    document.querySelector('#latency').textContent = data.latency_ms + ' ms'; document.querySelector('#answer').innerHTML = formatAnswer(data.answer);
    document.querySelector('.sources-section').classList.toggle('hidden', outOfScope); document.querySelector('.evidence').classList.toggle('hidden', outOfScope);
    document.querySelector('#citation-status').textContent = data.citation_valid ? 'Citations verified' : 'Citation check failed';
    document.querySelector('#citations').innerHTML = data.citations.length ? data.citations.map(sourceCard).join('') : '<p class="updates-empty">No citable evidence was retrieved for this question.</p>';
    document.querySelector('#evidence-list').innerHTML = data.retrieved_evidence.map(evidenceCard).join(''); result.classList.remove('hidden');
  } catch (error) {
    emptyState.classList.remove('hidden'); emptyState.innerHTML = '<div class="empty-rule"></div><p class="kicker">Unable to complete the review</p><h2>Try again in a moment.</h2><p>' + escapeHtml(error.message) + '</p>';
  } finally { setLoading(false); submit.disabled = false; submit.innerHTML = 'Analyse <span>↗</span>'; }
});
