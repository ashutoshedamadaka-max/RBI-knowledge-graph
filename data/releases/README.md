# Evaluated corpus release

`corpus-v2.zip` freezes the 88-document corpus used by the saved evaluations.
It contains 2,754 chunks, the 7,777-node / 10,424-edge graph, original source
files, processed pages, runtime corpus manifests, the saved register page, and
the OpenAI corpus embedding cache. It excludes API keys, evaluation cost history,
and stale extraction repair backups.

The archive SHA-256 is in `corpus-v2.zip.sha256`. Its internal
`release-manifest.json` gives every file's hash, counts, and corpus fingerprint.
The graph's hash matches `data/evaluation/answers-test-gpt-4o-mini.json`.

The Docker build runs `scripts/install_corpus_release.py` to verify the package
and seed `/service/data`. Render's free filesystem can then be recreated from
the image on each restart. Supabase remains responsible for mutable runtime
snapshots and PostgreSQL chunk rows; packaging does not migrate that database.
Newly ingested original files are still ephemeral on the free service. The
packaged graph and cached embeddings represent the evaluated release, rather
than an automatically rebuilt graph of future ingestions.

To verify installation locally, choose an empty, ignored data directory:

```powershell
.venv/Scripts/python.exe scripts/install_corpus_release.py --archive data/releases/corpus-v2.zip --checksum-file data/releases/corpus-v2.zip.sha256 --data-dir data/runtime/release-check
```

Do not run this installer against a live runtime directory. Updated corpus
releases require a new archive, checksum, validation, and deployment. Follow
`docs/production-cutover.md` for the separate database backup and migration.
