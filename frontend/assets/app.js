const apiBaseUrl = String(window.RBI_API_BASE_URL || '').replace(/\/+$/, '');
const apiUrl = (path) => apiBaseUrl + path;
const form = document.querySelector('#query-form');
const question = document.querySelector('#question');
const submit = document.querySelector('#submit');
const result = document.querySelector('#result');
const emptyState = document.querySelector('#empty-state');
const updatesView = document.querySelector('#updates-view');
const knowledgeStatus = document.querySelector('#knowledge-status');

function formatCheckTime(checks) {
  return checks.length ? new Date(checks[0].checked_at).toLocaleString() : 'No check recorded yet';
}

async function loadKnowledgeStatus() {
  try {
    const response = await fetch(apiUrl('/monitoring-status'));
    if (!response.ok) throw new Error('Status is temporarily unavailable.');
    const status = await response.json();
    const checks = status.last_checks || [];
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

document.querySelectorAll('[data-question]').forEach((button) => { button.addEventListener('click', () => { question.value = button.dataset.question; question.focus(); }); });
document.querySelector('#updates-toggle').addEventListener('click', async () => {
  updatesView.classList.toggle('hidden');
  if (updatesView.classList.contains('hidden')) return;
  try {
    const [updatesResponse, statusResponse] = await Promise.all([fetch(apiUrl('/regulatory-updates')), fetch(apiUrl('/monitoring-status'))]);
    if (!updatesResponse.ok || !statusResponse.ok) throw new Error('Regulatory updates are temporarily unavailable.');
    const updates = await updatesResponse.json();
    const status = await statusResponse.json();
    const checks = status.last_checks || [];
    document.querySelector('#monitoring-health').textContent = checks.length ? 'Last RBI check: ' + formatCheckTime(checks) : 'No successful check recorded';
    const changes = updates.length ? updates.map((update) => '<article class="citation"><span class="citation-index">' + escapeHtml(update.materiality[0]) + '</span><div><h3>' + escapeHtml(update.title) + '</h3><p>' + escapeHtml(update.change_type) + ' · ' + new Date(update.detected_at).toLocaleDateString() + '</p><p class="update-summary">' + escapeHtml(update.summary) + '</p></div><a href="' + escapeHtml(update.source_url) + '" target="_blank" rel="noreferrer">Evidence ↗</a></article>').join('') : '<p class="intro">No new or revised RBI lending documents were detected in the latest check.</p>';
    const sourceHealth = checks.length ? '<div class="source-health">' + checks.map((check) => '<span class="source-check ' + (check.status === 'NO_CHANGES' ? 'healthy' : 'attention') + '">' + escapeHtml(check.source_id.replace(/^rbi_/, '').replaceAll('_', ' ')) + ' · ' + escapeHtml(check.status.replaceAll('_', ' ').toLowerCase()) + '</span>').join('') + '</div>' : '';
    document.querySelector('#updates-list').innerHTML = changes + sourceHealth;
  } catch (error) { document.querySelector('#updates-list').innerHTML = '<p class="intro">' + escapeHtml(error.message) + '</p>'; }
});
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (character) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[character])); }
function formatAnswer(value) { return escapeHtml(value).replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/\n- (.+)/g, '<li>$1</li>').replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>').replace(/\n\n/g, '</p><p>').replace(/^/, '<p>').replace(/$/, '</p>'); }
function sourceCard(citation, index) { const source = citation.source_url ? '<a href="' + escapeHtml(citation.source_url) + '" target="_blank" rel="noreferrer">Open RBI source ↗</a>' : '<span></span>'; return '<article class="citation"><span class="citation-index">' + (index + 1) + '</span><div><h3>' + escapeHtml(citation.document_title) + '</h3><p>Page ' + citation.page_number + ' · ' + escapeHtml(citation.chunk_id) + '</p></div>' + source + '</article>'; }
function evidenceCard(item) { return '<article class="evidence-item"><strong>' + escapeHtml(item.document_title) + ' · page ' + item.page_number + ' · ' + escapeHtml(item.chunk_id) + '</strong><p>' + escapeHtml(item.text) + '</p></article>'; }
form.addEventListener('submit', async (event) => {
  event.preventDefault(); const value = question.value.trim(); if (!value) return; submit.disabled = true; submit.textContent = 'Reviewing…';
  try {
    const response = await fetch(apiUrl('/query'), { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ query:value }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'The question could not be processed.');
    emptyState.classList.add('hidden'); result.classList.remove('hidden'); const outOfScope = data.in_scope === false; const routePill = document.querySelector('#route-pill'); routePill.textContent = outOfScope ? 'OUTSIDE RBI LENDING SCOPE' : data.route + ' RETRIEVAL'; routePill.classList.toggle('out-of-scope', outOfScope); document.querySelector('#request-id').textContent = data.request_id; document.querySelector('#latency').textContent = data.latency_ms + ' ms'; document.querySelector('#answer').innerHTML = formatAnswer(data.answer); document.querySelector('.sources-section').classList.toggle('hidden', outOfScope); document.querySelector('.evidence').classList.toggle('hidden', outOfScope); document.querySelector('#citation-status').textContent = data.citation_valid ? 'Citations verified' : 'Citation check failed'; document.querySelector('#citations').innerHTML = data.citations.length ? data.citations.map(sourceCard).join('') : '<p class="intro">No citable evidence was retrieved for this question.</p>'; document.querySelector('#evidence-list').innerHTML = data.retrieved_evidence.map(evidenceCard).join('');
  } catch (error) { emptyState.classList.remove('hidden'); emptyState.innerHTML = '<div class="empty-icon">!</div><h2>Unable to complete the review</h2><p>' + escapeHtml(error.message) + '</p>'; result.classList.add('hidden'); }
  finally { submit.disabled = false; submit.innerHTML = 'Analyse <span>↗</span>'; }
});
