import json
from pathlib import Path

from app.config.settings import Settings


class DurableRuntimeState:
    """Persist the existing runtime repositories as atomic JSON snapshots in Postgres.

    The application keeps its tested local repositories during the migration, while this
    adapter makes their state survive stateless web-service restarts. A later migration can
    split these snapshots into dedicated relational tables without changing API contracts.
    """

    file_names = (
        "documents.json",
        "vectors.json",
        "knowledge_graph.json",
        "monitoring.json",
        "cost_events.json",
    )

    def __init__(self, settings: Settings) -> None:
        self.database_url = settings.database_url
        self.runtime_dir = settings.runtime_dir

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def restore(self) -> None:
        """Hydrate local runtime files from Postgres before services are constructed."""
        if not self.enabled:
            return
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            cursor.execute("SELECT state_key, payload FROM rbi_runtime_state")
            rows = {key: payload for key, payload in cursor.fetchall()}
        for file_name in self.file_names:
            payload = rows.get(file_name)
            if payload is not None:
                (self.runtime_dir / file_name).write_text(json.dumps(payload, indent=2))

    def sync(self) -> None:
        """Store the latest local repositories after a completed request."""
        if not self.enabled:
            return
        snapshots: list[tuple[str, object]] = []
        for file_name in self.file_names:
            path = self.runtime_dir / file_name
            if path.exists():
                snapshots.append((file_name, json.loads(path.read_text())))
        if not snapshots:
            return
        with self._connection() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            for key, payload in snapshots:
                cursor.execute(
                    """
                    INSERT INTO rbi_runtime_state (state_key, payload, updated_at)
                    VALUES (%s, %s::jsonb, now())
                    ON CONFLICT (state_key)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at
                    """,
                    (key, json.dumps(payload)),
                )

    def _connection(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for durable runtime state.")
        import psycopg
        return psycopg.connect(self.database_url)

    @staticmethod
    def _ensure_schema(cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rbi_runtime_state (
                state_key TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
