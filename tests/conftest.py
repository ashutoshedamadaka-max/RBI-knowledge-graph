import pytest

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep tests away from the real data directory and any configured database."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "isolated-data"))
    # An empty value overrides any DATABASE_URL in .env and disables durable sync.
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
