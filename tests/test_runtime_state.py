from contextlib import contextmanager

import pytest

from app.config.settings import Settings
from app.persistence.runtime_state import DurableRuntimeState


def test_sync_uploads_only_changes_and_retries_failed_transactions(tmp_path, monkeypatch):
    state = DurableRuntimeState(Settings(_env_file=None, data_dir=tmp_path, database_url="postgresql://unused"))
    state.runtime_dir.mkdir()
    path = state.runtime_dir / "documents.json"
    path.write_text("[]")
    writes = []
    fail = False
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, params=None):
            if params:
                writes.append(params[0])
    class Connection:
        def cursor(self): return Cursor()
    @contextmanager
    def connection():
        yield Connection()
        if fail:
            raise RuntimeError("commit failed")
    monkeypatch.setattr(state, "_connection", connection)
    state.sync()
    assert writes == ["documents.json"]
    state.sync()
    assert writes == ["documents.json"]
    path.write_text('[{"updated": true}]')
    fail = True
    with pytest.raises(RuntimeError): state.sync()
    fail = False
    state.sync()
    assert writes == ["documents.json"] * 3
