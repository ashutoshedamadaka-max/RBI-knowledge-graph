const form = document.querySelector('#query-form');
const question = document.querySelector('#question');
const submit = document.querySelector('#submit');
const result = document.querySelector('#result');
const emptyState = document.querySelector('#empty-state');

document.querySelectorAll('[data-question]').forEach((button) => {
  button.addEventListener('click', () => { question.value = button.dataset.question; question.focus(); });
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[character]));
}

function formatAnswer(value) {
  return escapeHtml(value)
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/\n- (.+)/g, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>');
}

function sourceCard(citation, index) {
  const source = citation.source_url
    ? '<a href="' + escapeHtml(citation.source_url) + '" target="_blank" rel="noreferrer">Open RBI source ↗</a>'
    : '<span></span>';
  return '<article class="citation"><span class="citation-index">' + (index + 1) + '</span><div><h3>' +
    escapeHtml(citation.document_title) + '</h3><p>Page ' + citation.page_number + ' · ' +
    escapeHtml(citation.chunk_id) + '</p></div>' + source + '</article>';
}

function evidenceCard(item) {
  return '<article class="evidence-item"><strong>' + escapeHtml(item.document_title) + ' · page ' +
    item.page_number + ' · ' + escapeHtml(item.chunk_id) + '</strong><p>' + escapeHtml(item.text) + '</p></article>';
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const value = question.value.trim();
  if (!value) return;
  submit.disabled = true;
  submit.textContent = 'Reviewing…';
  try {
    const response = await fetch('/query', { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ query:value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The question could not be processed.');
    emptyState.classList.add('hidden');
    result.classList.remove('hidden');
    document.querySelector('#route-pill').textContent = data.route + ' RETRIEVAL';
    document.querySelector('#request-id').textContent = data.request_id;
    document.querySelector('#latency').textContent = data.latency_ms + ' ms';
    document.querySelector('#answer').innerHTML = formatAnswer(data.answer);
    document.querySelector('#citation-status').textContent = data.citation_valid ? 'Citations verified' : 'Citation check failed';
    document.querySelector('#citations').innerHTML = data.citations.length
      ? data.citations.map(sourceCard).join('')
      : '<p class="intro">No citable evidence was retrieved for this question.</p>';
    document.querySelector('#evidence-list').innerHTML = data.retrieved_evidence.map(evidenceCard).join('');
  } catch (error) {
    emptyState.classList.remove('hidden');
    emptyState.innerHTML = '<div class="empty-icon">!</div><h2>Unable to complete the review</h2><p>' + escapeHtml(error.message) + '</p>';
    result.classList.add('hidden');
  } finally {
    submit.disabled = false;
    submit.innerHTML = 'Analyse <span>↗</span>';
  }
});

