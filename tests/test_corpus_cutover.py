import json
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg import sql

from app.config.settings import Settings
from app.models.chunks import ChunkMetadata
from app.persistence.runtime_state import DurableRuntimeState
from app.retrieval.vector_store import PostgresVectorStore
from scripts.stage_corpus_cutover import restore_backup_to_scratch, stage

pgserver = pytest.importorskip("pgserver")


@pytest.fixture
def connection(tmp_path):
    server = pgserver.get_server(str(tmp_path / "postgres"), cleanup_mode="stop")
    with psycopg.connect(server.get_uri(), autocommit=True) as connection:
        connection.execute("SET extra_float_digits=0")
        connection.execute(sql.SQL("ALTER DATABASE {} SET extra_float_digits=0").format(sql.Identifier(connection.info.dbname)))
        yield connection, server.get_uri()
    server.cleanup()


def backup():
    return {"chunks_table_existed": False, "chunks": [], "snapshots": [
        {"state_key": key, "payload": payload, "updated_at": datetime.now(timezone.utc).isoformat()}
        for key, payload in {"documents.json": [{"document_id": "old"}], "cost_events.json": [{"cost": 1}],
                             "extraction_repair_backup.json": {"stale": True}}.items()
    ]}


def candidate():
    chunk = ChunkMetadata(chunk_id="new-1", document_id="new", document_title="New direction",
                          page_number=1, chunk_index=0, text="An evaluated provision.").model_dump(mode="json")
    rows = [{"chunk": chunk, "embedding": [0.12345678901234567] + [0.0] * 255}]
    return {"rows": rows, "manifest": {"corpus_fingerprint": "verified-fixture"}, "snapshots": {
        "documents.json": [{"document_id": "new"}], "vectors.json": rows,
        "knowledge_graph.json": {"nodes": [], "edges": []}, "document_links.json": [], "monitoring.json": {}
    }}


def test_isolated_stage_and_application_writes_preserve_old_state(connection, tmp_path):
    conn, url = connection
    old = backup()
    restore_backup_to_scratch(conn, old)
    result = stage(conn, candidate(), old)
    assert result["live_documents"] == 1 and result["chunks"] == 1
    staged_store = PostgresVectorStore(url, schema="rbi_corpus_v2")
    assert staged_store._rows()[0]["embedding"] == candidate()["rows"][0]["embedding"]
    assert [row.chunk_id for row in staged_store.get_by_document_id("new")] == ["new-1"]
    old_store = PostgresVectorStore(url)
    assert old_store._rows() == []
    staged_store.apply_lifecycle("new", "WITHDRAWN")
    staged_store.set_in_force("new", None, None)
    staged_store.mark_document_not_current("new", "2026-10-22")
    assert conn.execute("SELECT chunk->>'lifecycle' FROM rbi_corpus_v2.chunks").fetchone()[0] == "WITHDRAWN"
    assert old_store._rows() == []

    settings = Settings(_env_file=None, data_dir=tmp_path / "runtime-check", database_url=url,
                        postgres_schema="rbi_corpus_v2")
    state = DurableRuntimeState(settings)
    state.restore()
    assert json.loads((settings.runtime_dir / "cost_events.json").read_text()) == [{"cost": 1}]
    assert not (settings.runtime_dir / "extraction_repair_backup.json").exists()
    (settings.runtime_dir / "documents.json").write_text('[{"document_id":"new","reviewed":true}]')
    state.sync()
    assert conn.execute("SELECT payload FROM public.rbi_runtime_state WHERE state_key='documents.json'").fetchone()[0] == [{"document_id": "old"}]
    assert conn.execute("SELECT payload FROM rbi_corpus_v2.rbi_runtime_state WHERE state_key='documents.json'").fetchone()[0][0]["reviewed"]
    staged_store.remove_document_ids({"new"})
    assert staged_store._rows() == []
    assert old_store._rows() == []


def test_postgres_snapshots_leave_legacy_vector_state_untouched(connection, tmp_path):
    conn, url = connection
    old = backup()
    restore_backup_to_scratch(conn, old)
    stage(conn, candidate(), old)
    settings = Settings(_env_file=None, data_dir=tmp_path / "postgres-runtime", database_url=url,
                        postgres_schema="rbi_corpus_v2", vector_backend="postgres")
    settings.runtime_dir.mkdir(parents=True)
    legacy = settings.runtime_dir / "vectors.json"
    legacy.write_text("This unused snapshot must never be parsed or replaced.")
    state = DurableRuntimeState(settings)
    state.restore()
    assert legacy.read_text().startswith("This unused snapshot")
    (settings.runtime_dir / "documents.json").write_text('[{"document_id":"new","reviewed":true}]')
    state.sync()
    assert conn.execute("SELECT payload FROM rbi_corpus_v2.rbi_runtime_state WHERE state_key='vectors.json'").fetchone()[0] == candidate()["rows"]
    assert conn.execute("SELECT payload FROM rbi_corpus_v2.rbi_runtime_state WHERE state_key='documents.json'").fetchone()[0][0]["reviewed"]
    assert PostgresVectorStore(url, schema="rbi_corpus_v2")._chunks() == [candidate()["rows"][0]["chunk"]]


def test_failed_stage_rolls_back_all_new_objects(connection):
    conn, _ = connection
    old = backup()
    restore_backup_to_scratch(conn, old)
    invalid = candidate()
    invalid["rows"].append(invalid["rows"][0])
    with pytest.raises(psycopg.errors.UniqueViolation):
        stage(conn, invalid, old)
    assert conn.execute("SELECT to_regnamespace('rbi_corpus_v2')").fetchone()[0] is None
    assert conn.execute("SELECT payload FROM public.rbi_runtime_state WHERE state_key='documents.json'").fetchone()[0] == [{"document_id": "old"}]


def test_live_changes_and_existing_staging_are_never_overwritten(connection):
    conn, _ = connection
    old = backup()
    restore_backup_to_scratch(conn, old)
    conn.execute("UPDATE public.rbi_runtime_state SET payload='[]' WHERE state_key='documents.json'")
    with pytest.raises(ValueError, match="changed after the backup"):
        stage(conn, candidate(), old)
    assert conn.execute("SELECT to_regnamespace('rbi_corpus_v2')").fetchone()[0] is None
    conn.execute("UPDATE public.rbi_runtime_state SET payload='[{\"document_id\":\"old\"}]' WHERE state_key='documents.json'")
    stage(conn, candidate(), old)
    with pytest.raises(ValueError, match="already exists"):
        stage(conn, candidate(), old)
    assert conn.execute("SELECT count(*) FROM rbi_corpus_v2.chunks").fetchone()[0] == 1
