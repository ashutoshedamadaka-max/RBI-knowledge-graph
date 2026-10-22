import httpx
import pytest

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep tests away from the real data directory and any configured database."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "isolated-data"))
    # An empty value overrides any DATABASE_URL in .env and disables durable sync.
    monkeypatch.setenv("DATABASE_URL", "")
    # Tests never make paid calls: empty values override the keys in .env.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("COHERE_API_KEY", "")
    real_post = httpx.post

    def guarded_post(url, *args, **kwargs):
        if any(host in str(url) for host in ("api.openai.com", "api.cohere.com")):
            raise RuntimeError(f"A test tried a paid API call: {url}")
        return real_post(url, *args, **kwargs)

    monkeypatch.setattr(httpx, "post", guarded_post)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
