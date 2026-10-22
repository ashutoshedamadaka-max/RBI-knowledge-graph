"""Stage a verified corpus in an isolated schema; never replace the live tables.

Reads production credentials only from the explicitly named ignored env file.
Requires a checksum-verified application backup. Existing staging schemas are
never overwritten. The old API continues to use public; the rebuilt Docker
image selects rbi_corpus_v2 through POSTGRES_SCHEMA.
"""

import argparse
import gzip
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from psycopg.types.json import Jsonb

CORPUS_KEYS = ("documents.json", "vectors.json", "knowledge_graph.json",
               "document_links.json", "monitoring.json")


def read_backup(path: Path) -> dict:
    expected = Path(str(path) + ".sha256").read_text().split()[0]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Application backup checksum mismatch.")
    backup = json.loads(gzip.decompress(data))
    if backup["format"] != "rbi-application-backup-v1":
        raise ValueError("Unrecognized application backup format.")
    return backup


def read_release(archive: Path, checksum: Path) -> dict:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum.read_text().split()[0]:
        raise ValueError("Corpus release checksum mismatch.")
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("release-manifest.json"))
        snapshots = {}
        for key in CORPUS_KEYS:
            name = "runtime/" + key
            payload = bundle.read(name)
            if hashlib.sha256(payload).hexdigest() != manifest["files"][name]:
                raise ValueError(f"Corpus snapshot checksum mismatch: {key}")
            snapshots[key] = json.loads(payload)
    documents, rows = snapshots["documents.json"], snapshots["vectors.json"]
    ids = {document["document_id"] for document in documents}
    fingerprint = hashlib.sha256("".join(sorted(
        f"{document['document_id']}:{document['content_hash']}" for document in documents
    )).encode()).hexdigest()
    if (len(documents) != manifest["documents"] or len(ids) != len(documents)
            or len(rows) != manifest["chunks"]
            or len({row["chunk"]["chunk_id"] for row in rows}) != len(rows)
            or any(row["chunk"]["document_id"] not in ids for row in rows)
            or fingerprint != manifest["corpus_fingerprint"]):
        raise ValueError("Corpus release counts, references or fingerprint are invalid.")
    return {"manifest": manifest, "snapshots": snapshots, "rows": rows}


def restore_backup_to_scratch(connection, backup: dict) -> None:
    """Restore into a fresh scratch database only; refuses existing tables."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("CREATE TABLE public.rbi_runtime_state (state_key text PRIMARY KEY, "
                       "payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        cursor.executemany("INSERT INTO public.rbi_runtime_state VALUES (%s,%s,%s)", [
            (row["state_key"], Jsonb(row["payload"]), row["updated_at"]) for row in backup["snapshots"]
        ])
        if backup["chunks_table_existed"]:
            cursor.execute("CREATE TABLE public.chunks (chunk_id text PRIMARY KEY, document_id text NOT NULL, "
                           "chunk jsonb NOT NULL, embedding double precision[] NOT NULL)")
            cursor.executemany("INSERT INTO public.chunks VALUES (%s,%s,%s,%s)", [
                (row["chunk_id"], row["document_id"], Jsonb(row["chunk"]), row["embedding"])
                for row in backup["chunks"]
            ])
        restored = dict(cursor.execute("SELECT state_key,payload FROM public.rbi_runtime_state").fetchall())
        if restored != {row["state_key"]: row["payload"] for row in backup["snapshots"]}:
            raise ValueError("Scratch restore differs from the backup.")


def stage(connection, candidate: dict, backup: dict, schema: str = "rbi_corpus_v2") -> dict:
    if schema in {"public", "auth", "storage", "information_schema"} or schema.startswith("pg_"):
        raise ValueError("The target must be an isolated application schema.")
    runtime = sql.Identifier(schema, "rbi_runtime_state")
    chunks = sql.Identifier(schema, "chunks")
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('rbi-corpus-stage-v2'))")
        if cursor.execute("SELECT to_regnamespace(%s)", (schema,)).fetchone()[0] is not None:
            raise ValueError("Target schema already exists; refusing to overwrite it.")
        source = cursor.execute("SELECT state_key,payload,updated_at FROM public.rbi_runtime_state").fetchall()
        source_payloads = {key: payload for key, payload, _ in source}
        backed_up = {row["state_key"]: row["payload"] for row in backup["snapshots"]}
        if source_payloads.get("documents.json") != backed_up.get("documents.json"):
            raise ValueError("Live documents changed after the backup; take a fresh backup first.")
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("CREATE TABLE {} (LIKE public.rbi_runtime_state INCLUDING ALL)").format(runtime))
        cursor.execute(sql.SQL("CREATE TABLE {} (chunk_id text PRIMARY KEY, document_id text NOT NULL, "
                               "chunk jsonb NOT NULL, embedding double precision[] NOT NULL)").format(chunks))
        cursor.execute(sql.SQL("CREATE INDEX chunks_document_id ON {} (document_id)").format(chunks))
        # Supabase default privileges must not expose staged state through API roles.
        for role in ("PUBLIC", "anon", "authenticated"):
            if role == "PUBLIC" or cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                recipient = sql.SQL("PUBLIC") if role == "PUBLIC" else sql.Identifier(role)
                cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(sql.Identifier(schema), recipient))
                cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(sql.Identifier(schema), recipient))
        for table in (runtime, chunks):
            cursor.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(table))
        # Keep production cost history and any other non-corpus snapshots.
        payloads = {key: (payload, updated_at) for key, payload, updated_at in source
                    if key != "extraction_repair_backup.json"}
        now = datetime.now(timezone.utc)
        payloads.update({key: (payload, now) for key, payload in candidate["snapshots"].items()})
        cursor.executemany(sql.SQL("INSERT INTO {} VALUES (%s,%s,%s)").format(runtime), [
            (key, Jsonb(payload), updated_at) for key, (payload, updated_at) in payloads.items()
        ])
        with cursor.copy(sql.SQL("COPY {} (chunk_id,document_id,chunk,embedding) FROM STDIN").format(chunks)) as copy:
            for row in candidate["rows"]:
                copy.write_row((row["chunk"]["chunk_id"], row["chunk"]["document_id"],
                                Jsonb(row["chunk"]), row["embedding"]))
        staged = dict(cursor.execute(sql.SQL("SELECT state_key,payload FROM {}").format(runtime)).fetchall())
        if staged != {key: payload for key, (payload, _) in payloads.items()}:
            raise ValueError("Staged snapshots failed exact round-trip verification.")
        # Supabase sets extra_float_digits=0; binary results preserve every float8 bit.
        stored_rows = cursor.execute(sql.SQL("SELECT chunk,embedding FROM {} ORDER BY chunk_id").format(chunks), binary=True).fetchall()
        expected_rows = sorted(candidate["rows"], key=lambda row: row["chunk"]["chunk_id"])
        if [(row["chunk"], row["embedding"]) for row in expected_rows] != stored_rows:
            raise ValueError("Staged chunks failed exact round-trip verification.")
        unchanged = dict(cursor.execute("SELECT state_key,payload FROM public.rbi_runtime_state").fetchall())
        if unchanged.get("documents.json") != source_payloads.get("documents.json"):
            raise ValueError("Live documents changed while staging; retry from a fresh backup.")
    return {"schema": schema, "documents": len(candidate["snapshots"]["documents.json"]),
            "chunks": len(candidate["rows"]), "snapshot_keys": sorted(payloads),
            "corpus_fingerprint": candidate["manifest"]["corpus_fingerprint"],
            "live_documents": len(source_payloads["documents.json"]), "live_tables_replaced": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-env", type=Path, default=Path("data/runtime/production.env"))
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=Path("data/releases/corpus-v2.zip"))
    parser.add_argument("--checksum", type=Path, default=Path("data/releases/corpus-v2.zip.sha256"))
    args = parser.parse_args()
    url = dotenv_values(args.database_env).get("DATABASE_URL")
    if not url:
        parser.error("The explicitly selected connection file has no DATABASE_URL.")
    try:
        backup = read_backup(args.backup)
        candidate = read_release(args.archive, args.checksum)
        with psycopg.connect(url, autocommit=True, connect_timeout=20) as connection:
            print(json.dumps(stage(connection, candidate, backup)))
    except Exception as exc:
        message = str(exc).replace(url, "[redacted connection]")
        password = urlsplit(url).password
        if password:
            for value in (password, unquote(password)):
                message = message.replace(value, "[redacted]")
        print(json.dumps({"error_type": type(exc).__name__, "message": message}))
        sys.exit(1)


if __name__ == "__main__":
    main()
