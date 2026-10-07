# Answer quality and persistence repair

The sample priority-sector amendment answer contained RBI website navigation,
not a usable explanation. Notification HTML now selects `#NotificationUser`,
preserving tables and excluding surrounding website navigation. The answer
prompt requests a short plain-English explanation of actual supported changes.
An explicit model abstention is no longer replaced by quoted excerpts merely
because retrieval found chunks. The deterministic fallback rejects known page
chrome, excessively long sentences, and incomplete “modified as below” intros.
Citation ID validation alone is not a semantic correctness guarantee.

## Existing evidence

On startup, `repair_legacy_notifications` checks indexed HTML for known legacy
navigation markers. It uses captured raw HTML, cached processed text, or
reconstructed chunks with verified overlap. It never fetches today's page to
rewrite a historical version. Text-only recovery requires an official RBI
circular identifier to locate the body. Unverifiable boundaries and custom
non-deterministic graph edges are skipped and logged for review.

Affected chunks are re-embedded and deterministic graph provenance is rebuilt.
Document identity, lifecycle, dates, and human approval evidence are unchanged.
The first pre-repair vector/graph snapshots are retained in
`data/runtime/extraction_repair_backup.json`, also included in durable storage.
Per-document failures roll back index files and are logged; a failed repair
does not stop the server. Do not restore the backup over newer data without
checking changes made since the repair. This is an extraction repair, not a
new regulatory version or status approval.

## Waiting time

Health probes and other read-only requests no longer upload the runtime corpus.
Database synchronization saves only files whose content changed, and marks
them saved only after a successful transaction. Streamed queries save after
their output finishes, off the event loop. These changes remove unnecessary
work but do not establish a measured production speed improvement. Free-host
startup delay, network time, and model generation still need live measurement.

## Verification

Regression tests cover notification-body/table extraction, navigation-only
abstention, preserved model abstention, offline repair with unchanged approvals,
backup, verified overlap reconstruction, skipped ambiguous boundaries, rollback,
changed-file persistence and commit retry, no persistence on reads, and save
ordering after streamed generation. No lifecycle rule or retrieval authority
filter was relaxed. No production approvals are changed by this patch.
