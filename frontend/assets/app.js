const base = String(window.RBI_API_BASE_URL || '').replace(/\/+$/, '');
const api = (path) => base + path;
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
let lastQuery = '';
let latestDocuments = [];

function dateText(value) { return value ? new Date(value).toLocaleString() : 'No successful check recorded'; }
function showResearchMode(query) { $('#app-shell').classList.add('research-mode'); $('#loading-query').textContent = query; $('#workspace-query').textContent = query; }
function citationButton(id, index) { return '<button class="citation-button" type="button" data-citation="' + escapeHtml(id) + '" aria-label="View source ' + (index + 1) + '">[' + (index + 1) + ']</button>'; }
function citationMap(data) { return new Map((data.citations || []).map((citation, index) => [citation.chunk_id, index])); }
function claimHtml(claim, index, sources) { const citations = (claim.citation_ids || []).map((id) => citationButton(id, sources.get(id) ?? index)).join(''); return '<div class="claim"><span class="claim-number">' + String(index + 1).padStart(2, '0') + '</span><p>' + escapeHtml(claim.text) + citations + '</p></div>'; }
function selectSource(chunkId) { const card = document.getElementById('source-' + chunkId); if (!card) return; $$('.source-card').forEach((item) => item.classList.remove('selected')); card.classList.add('selected'); card.scrollIntoView({behavior:'smooth', block:'nearest'}); }
function $$(selector) { return [...document.querySelectorAll(selector)]; }

async function loadStatus() {
  try {
    const [statusResponse, documentsResponse] = await Promise.all([fetch(api('/monitoring-status')), fetch(api('/documents'))]);
    if (!statusResponse.ok || !documentsResponse.ok) throw new Error();
    const status = await statusResponse.json(); const documentList = await documentsResponse.json(); latestDocuments = documentList.documents || [];
    const checks = status.last_checks || [];
    $('#document-count').textContent = status.document_count + ' RBI documents indexed'; $('#source-count').textContent = status.tracked_source_count + ' official sources monitored';
    $('#topic-labels').innerHTML = (status.topics || []).slice(0, 5).map((topic) => '<span>' + escapeHtml(topic) + '</span>').join('');
    $('#knowledge-summary').textContent = 'Last checked ' + dateText(checks[0]?.checked_at); $('#header-last-check').textContent = 'Last synced: ' + dateText(checks[0]?.checked_at);
    $('#knowledge-health').textContent = status.health === 'healthy' ? '● Live' : 'Needs review';
  } catch { $('#document-count').textContent = 'Knowledge base temporarily unavailable'; $('#source-count').textContent = 'Status will retry on refresh'; $('#knowledge-health').textContent = 'Unavailable'; }
}
function sourceCard(citation, index, evidence) {
  const chunk = evidence.find((item) => item.chunk_id === citation.chunk_id); const excerpt = chunk?.text ? chunk.text.slice(0, 300) + (chunk.text.length > 300 ? '…' : '') : 'Relevant excerpt unavailable.';
  return '<article class="source-card" id="source-' + escapeHtml(citation.chunk_id) + '"><header><span class="index">' + (index + 1) + '</span><div><h3>' + escapeHtml(citation.document_title) + '</h3><small>Page ' + escapeHtml(citation.page_number) + '</small></div></header><blockquote>' + escapeHtml(excerpt) + '</blockquote>' + (citation.source_url ? '<a href="' + escapeHtml(citation.source_url) + '" target="_blank" rel="noreferrer">View original RBI source →</a>' : '') + '</article>';
}
function graphHtml(graph, citationIndexes) {
  if (!graph?.edges?.length) return '<p class="relationship-empty">No query-relevant regulatory relationships were retrieved for this question. The answer and sources remain the primary evidence.</p>';
  const names = new Map((graph.nodes || []).map((node) => [node.node_id, node.name]));
  return '<div class="relationship-list">' + graph.edges.map((edge) => '<article class="relationship-edge"><strong>' + escapeHtml(names.get(edge.source_id) || edge.source_id) + '</strong><span>' + escapeHtml(edge.relationship_type.replaceAll('_', ' ').toLowerCase()) + ' →</span><strong>' + escapeHtml(names.get(edge.target_id) || edge.target_id) + '</strong>' + (citationIndexes.has(edge.source_chunk_id) ? citationButton(edge.source_chunk_id, citationIndexes.get(edge.source_chunk_id)) : '') + '</article>').join('') + '</div>';
}
function renderAnswer(data) {
  const research = data.research; const sourceIndexes = citationMap(data); const citations = data.citations || [];
  const insufficient = research?.status === 'insufficient_evidence'; const outOfScope = research?.status === 'out_of_scope';
  $('#answer-title').textContent = insufficient ? 'Insufficient evidence' : outOfScope ? 'Outside the knowledge base' : 'Grounded answer';
  $('#evidence-badge').textContent = citations.length ? 'Based on ' + citations.length + ' RBI source' + (citations.length === 1 ? '' : 's') : outOfScope ? 'RBI lending scope' : 'No verified source';
  const direct = research?.direct_answer; let html = '';
  if (direct) html += '<section class="direct-answer"><h3>' + (outOfScope ? 'Knowledge-base boundary' : insufficient ? 'What we found' : 'Direct answer') + '</h3><p>' + escapeHtml(direct.text) + (direct.citation_ids || []).map((id) => citationButton(id, sourceIndexes.get(id) || 0)).join('') + '</p></section>';
  (research?.sections || []).forEach((section) => { if (section.claims?.length) html += '<section class="answer-section"><h3>' + escapeHtml(section.title) + '</h3>' + section.claims.map((claim, index) => claimHtml(claim, index, sourceIndexes)).join('') + '</section>'; });
  if (!html) html = '<section class="direct-answer"><h3>Research result</h3><p>No structured answer was returned. Please retry the research request.</p></section>';
  $('#structured-answer').innerHTML = html;
  $('#sources-tab').innerHTML = citations.length ? citations.map((citation, index) => sourceCard(citation, index, data.retrieved_evidence || [])).join('') : '<p class="relationship-empty">No citable RBI source was retrieved for this request.</p>';
  $('#relationships-tab').innerHTML = graphHtml(research?.graph_context, sourceIndexes); $('#source-tab-count').textContent = citations.length ? '(' + citations.length + ')' : ''; $('#graph-tab-count').textContent = research?.graph_context?.edges?.length ? '(' + research.graph_context.edges.length + ')' : '';
  const related = research?.related_questions || []; $('#related-questions').classList.toggle('hidden', !related.length); $('#related-question-list').innerHTML = related.map((item) => '<button type="button" data-follow-up="' + escapeHtml(item) + '">' + escapeHtml(item) + ' →</button>').join('');
  $('#research-trace').innerHTML = [citations.length ? citations.length + ' official source' + (citations.length === 1 ? '' : 's') + ' retrieved' : null, data.citation_valid ? 'Citations verified' : null, research?.graph_context?.edges?.length ? research.graph_context.edges.length + ' regulatory relationship' + (research.graph_context.edges.length === 1 ? '' : 's') + ' found' : null].filter(Boolean).map((item) => '<span>✓ ' + escapeHtml(item) + '</span>').join('');
  $$('.citation-button').forEach((button) => button.addEventListener('click', () => { $('.evidence-tabs button[data-tab="sources"]').click(); selectSource(button.dataset.citation); }));
  $$('[data-follow-up]').forEach((button) => button.addEventListener('click', () => { $('#question').value = button.dataset.followUp; $('#query-form').requestSubmit(); }));
}
function showError(message) { $('#research-error').innerHTML = '<h2>We couldn’t complete this research request.</h2><p>' + escapeHtml(message) + '</p><button id="retry-research" type="button">Try again</button>'; $('#research-error').classList.remove('hidden'); $('#retry-research').addEventListener('click', () => $('#query-form').requestSubmit()); }
function setLoading(loading) { $('#analysis-state').classList.toggle('hidden', !loading); if (loading) $('#result').classList.add('hidden'); }

$('#query-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const query = $('#question').value.trim(); if (!query) return; lastQuery = query; showResearchMode(query); $('#submit').disabled = true; setLoading(true); $('#empty-state').classList.add('hidden'); $('#research-error').classList.add('hidden');
  try { const response = await fetch(api('/query'), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query})}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'The RBI research service is temporarily unavailable.'); renderAnswer(data); $('#result').classList.remove('hidden'); }
  catch (error) { $('#result').classList.remove('hidden'); showError(error.message); }
  finally { setLoading(false); $('#submit').disabled = false; }
});
$$('[data-question]').forEach((button) => button.addEventListener('click', () => { $('#question').value = button.dataset.question; $('#question').focus(); }));
$('#new-research').addEventListener('click', () => { $('#app-shell').classList.remove('research-mode'); $('#result').classList.add('hidden'); $('#empty-state').classList.remove('hidden'); $('#question').focus(); window.scrollTo({top:0,behavior:'smooth'}); });
$$('.evidence-tabs button').forEach((button) => button.addEventListener('click', () => { $$('.evidence-tabs button').forEach((item) => item.classList.toggle('active', item === button)); $('#sources-tab').classList.toggle('hidden', button.dataset.tab !== 'sources'); $('#relationships-tab').classList.toggle('hidden', button.dataset.tab !== 'relationships'); }));
$('#updates-toggle').addEventListener('click', async () => { const view = $('#updates-view'); view.classList.toggle('hidden'); if (view.classList.contains('hidden')) return; try { const [updatesResponse,statusResponse] = await Promise.all([fetch(api('/regulatory-updates')),fetch(api('/monitoring-status'))]); const updates=await updatesResponse.json(), status=await statusResponse.json(), checks=status.last_checks||[]; $('#monitoring-health').textContent=checks.length?'Last check '+dateText(checks[0].checked_at):'No check recorded'; $('#updates-list').innerHTML=updates.length?updates.map((update)=>'<article class="source-card"><h3>'+escapeHtml(update.title)+'</h3><small>'+escapeHtml(update.change_type)+'</small><blockquote>'+escapeHtml(update.summary)+'</blockquote><a href="'+escapeHtml(update.source_url)+'" target="_blank" rel="noreferrer">View original RBI source →</a></article>').join(''):'<p class="relationship-empty">No material new or revised RBI lending documents were detected in the latest check.</p>'; } catch { $('#updates-list').innerHTML='<p class="relationship-empty">Regulatory updates are temporarily unavailable.</p>'; }});
function openCatalog() { const dialog=$('#source-catalog'); $('#catalog-content').innerHTML=latestDocuments.length?latestDocuments.map((document)=>'<article class="catalog-card"><h3>'+escapeHtml(document.title)+'</h3><p>'+(document.page_count?'Pages '+escapeHtml(document.page_count)+' · ':'')+'Indexed RBI material</p>'+(document.source_url?'<a href="'+escapeHtml(document.source_url)+'" target="_blank" rel="noreferrer">Open original source →</a>':'')+'</article>').join(''):'<p class="relationship-empty">Document details are not available yet. Refresh after the knowledge base loads.</p>'; dialog.showModal(); }
$('#view-all-sources').addEventListener('click',openCatalog); $('#source-catalog-toggle').addEventListener('click',openCatalog); $('#close-source-catalog').addEventListener('click',()=>$('#source-catalog').close());
loadStatus();
