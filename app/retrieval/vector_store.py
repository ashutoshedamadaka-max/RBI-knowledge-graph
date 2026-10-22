import json
import re
from datetime import date
from pathlib import Path

from app import clock
from app.embeddings.hashing import HashingEmbedder
from app.models.chunks import ChunkMetadata, VectorSearchResult


def in_force_on(chunk: dict, day: date) -> bool:
    """Whether a stored chunk's rule is in force on ``day`` (open-ended when a bound is unknown)."""
    start, end = chunk.get("in_force_from"), chunk.get("in_force_to")
    return (not start or date.fromisoformat(start) <= day) and (not end or day < date.fromisoformat(end))


def is_current_guidance(chunk: dict, day: date) -> bool:
    """Whether a chunk's rule applied on ``day``.

    Today or later: operative status, the latest version of its page, and in force. A past day:
    in force on that day by its in-force window, even if it was withdrawn or replaced since, as
    long as its status was ever established (not "review required") and its page version was
    not yet retired then.
    """
    if day >= clock.now().date():
        return bool(chunk.get("authority_current", False)) and chunk.get("is_current", True) is not False \
            and in_force_on(chunk, day)
    retired = chunk.get("valid_to")
    return chunk.get("lifecycle") not in UNSETTLED and in_force_on(chunk, day) \
        and (not retired or day < date.fromisoformat(str(retired)[:10]))


UNSETTLED = {"REVIEW_REQUIRED", "UNKNOWN"}  # status never established: not a rule on any date


def is_upcoming(chunk: dict, day: date) -> bool:
    """Operative and latest, but taking effect after ``day``."""
    start = chunk.get("in_force_from")
    return bool(chunk.get("authority_current", False)) and chunk.get("is_current", True) is not False \
        and bool(start) and date.fromisoformat(start) > day


_ROWS: dict = {}  # the last parsed file store, shared by every request


class LocalVectorStore:
    """Filesystem-backed vector index used by the local-first development mode."""

    def __init__(self, path: Path, embedder: HashingEmbedder | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or HashingEmbedder()

    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def _rows(self) -> list[dict]:
        """Rows for read-only use, parsed once per version of the file (a 2,754-chunk store is ~22 MB of JSON
        and was parsed several times per question). Writers use _read(), so they never mutate this copy."""
        if not self.path.exists():
            return []
        stamp = self.path.stat()
        key = (str(self.path), stamp.st_mtime_ns, stamp.st_size)
        if _ROWS.get("key") != key:
            _ROWS.update(key=key, rows=self._read())
        return _ROWS["rows"]

    def upsert(self, chunks: list[ChunkMetadata]) -> None:
        indexed = {row["chunk"]["chunk_id"]: row for row in self._read()}
        for chunk in chunks:
            indexed[chunk.chunk_id] = {
                "chunk": chunk.model_dump(mode="json"),
                "embedding": self.embedder.embed(chunk.text),
            }
        self.path.write_text(json.dumps(list(indexed.values()), indent=2))

    @staticmethod
    def _keywords(value: str) -> set[str]:
        """Return meaningful terms for a small, explainable lexical relevance signal."""
        stop_words = {
            "about", "after", "against", "among", "and", "are", "can", "does", "for",
            "from", "how", "into", "must", "of", "on", "or", "rbi", "the", "to",
            "under", "what", "when", "which", "with", "would",
        }
        return {
            word
            for word in re.findall(r"[a-z0-9]{3,}", value.lower())
            if word not in stop_words
        }

    @classmethod
    def _lexical_score(cls, query_terms: set[str], text: str, title: str) -> float:
        """Reward direct term matches, especially when the official document title matches."""
        if not query_terms:
            return 0.0
        text_overlap = len(query_terms & cls._keywords(text)) / len(query_terms)
        title_overlap = len(query_terms & cls._keywords(title)) / len(query_terms)
        return (0.55 * text_overlap) + (0.45 * title_overlap)

    def search(self, query: str, top_k: int = 5, current_only: bool = True, as_of: date | None = None,
               document_ids: set[str] | None = None, upcoming_only: bool = False) -> list[VectorSearchResult]:
        """Rank chunks for ``query``.

        ``current_only`` keeps rules in force on ``as_of`` (default today): operative status,
        latest version of the page, inside the in-force window. ``upcoming_only`` instead keeps
        operative rules that take effect later.
        """
        if not query.strip():
            return []
        query_embedding = self.embedder.embed(query)
        query_terms = self._keywords(query)
        matches = []
        day = as_of or clock.now().date()
        for row in self._rows():
            chunk = row["chunk"]
            if document_ids is not None and chunk["document_id"] not in document_ids:
                continue
            if upcoming_only:
                if not is_upcoming(chunk, day):
                    continue
            elif current_only and not is_current_guidance(chunk, day):
                continue
            vector_score = max(0.0, self.embedder.similarity(query_embedding, row["embedding"]))
            lexical_score = self._lexical_score(query_terms, chunk["text"], chunk["document_title"])
            # Semantic similarity remains the primary signal, while exact lending-topic and
            # official-document-title matches prevent unrelated boilerplate from winning.
            relevance_score = (0.55 * vector_score) + (0.45 * lexical_score)
            matches.append(VectorSearchResult(**chunk, similarity_score=round(relevance_score, 6)))
        return sorted(matches, key=lambda result: result.similarity_score, reverse=True)[:top_k]

    def sections(self, chunks: list[ChunkMetadata], max_tokens: int = 1500) -> dict[str, str]:
        """For each chunk with a parent section, the whole section's text (capped): small chunks are
        retrieved, the section around them is what the answer step reads. Citations stay on the chunk."""
        from app.ingestion.chunkers import count_tokens

        wanted = {chunk.parent_id for chunk in chunks if chunk.parent_id}
        if not wanted:
            return {}
        members: dict[str, list[dict]] = {}
        for row in self._rows():
            if row["chunk"].get("parent_id") in wanted:
                members.setdefault(row["chunk"]["parent_id"], []).append(row["chunk"])
        out = {}
        for chunk in chunks:
            siblings = sorted(members.get(chunk.parent_id, []), key=lambda item: item["chunk_index"])
            if len(siblings) < 2:
                continue
            heading = f"[{chunk.heading_path}]\n" if chunk.heading_path else ""
            text, used = heading, count_tokens(heading)
            for sibling in siblings:
                body = sibling["text"].removeprefix(heading)
                cost = count_tokens(body)
                if used + cost > max_tokens:
                    break
                text, used = text + body + "\n", used + cost
            out[chunk.chunk_id] = text.strip()
        return out

    def get_by_ids(self, chunk_ids: list[str]) -> list[ChunkMetadata]:
        wanted = set(chunk_ids)
        return [ChunkMetadata.model_validate(row["chunk"]) for row in self._rows() if row["chunk"]["chunk_id"] in wanted]

    def get_by_document_id(self, document_id: str) -> list[ChunkMetadata]:
        return [ChunkMetadata.model_validate(row["chunk"]) for row in self._rows() if row["chunk"]["document_id"] == document_id]

    def mark_document_current(self, document_id: str) -> None:
        rows = self._read()
        for row in rows:
            if row["chunk"]["document_id"] == document_id:
                row["chunk"]["is_current"] = True
                row["chunk"]["valid_to"] = None
        self.path.write_text(json.dumps(rows, indent=2))

    def mark_document_not_current(self, document_id: str, valid_to: str) -> None:
        rows = self._read()
        for row in rows:
            if row["chunk"]["document_id"] == document_id:
                row["chunk"]["is_current"] = False
                row["chunk"]["valid_to"] = valid_to
        self.path.write_text(json.dumps(rows, indent=2))

    def set_in_force(self, document_id: str, start: date | None, end: date | None) -> None:
        rows = self._read()
        for row in rows:
            if row["chunk"]["document_id"] == document_id:
                row["chunk"]["in_force_from"] = start.isoformat() if start else None
                row["chunk"]["in_force_to"] = end.isoformat() if end else None
        self.path.write_text(json.dumps(rows, indent=2))

    def apply_lifecycle(self, document_id: str, lifecycle: str) -> None:
        rows = self._read()
        authority_current = lifecycle in {"ACTIVE", "AMENDED"}
        for row in rows:
            if row["chunk"]["document_id"] == document_id:
                row["chunk"]["lifecycle"] = lifecycle
                row["chunk"]["authority_current"] = authority_current
        self.path.write_text(json.dumps(rows, indent=2))

    def remove_document_ids(self, document_ids: set[str]) -> None:
        if not document_ids:
            return
        rows = [row for row in self._read() if row["chunk"]["document_id"] not in document_ids]
        self.path.write_text(json.dumps(rows, indent=2))


class PostgresVectorStore(LocalVectorStore):
    """The same index in PostgreSQL: one row per chunk, so a write touches only its own rows.

    Search and scoring are inherited unchanged, so rankings are identical to the file
    store (rung 0 of the retrieval ladder). Embeddings are stored as float8 arrays, not
    pgvector's float4, so scores match exactly; the dense rungs add a pgvector column.
    """

    def __init__(self, database_url: str, embedder: HashingEmbedder | None = None) -> None:
        self.database_url = database_url
        self.embedder = embedder or HashingEmbedder()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS chunks (chunk_id text PRIMARY KEY, document_id text NOT NULL, "
                "chunk jsonb NOT NULL, embedding double precision[] NOT NULL)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS chunks_document_id ON chunks (document_id)")

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, autocommit=True)

    def _read(self) -> list[dict]:
        # ponytail: full scan per search, like the file store; the dense rungs add indexed search.
        with self._connect() as connection:
            rows = connection.execute("SELECT chunk, embedding FROM chunks ORDER BY chunk_id").fetchall()
        return [{"chunk": chunk, "embedding": embedding} for chunk, embedding in rows]

    def _rows(self) -> list[dict]:
        return self._read()  # the database is the source of truth on every read

    def upsert(self, chunks: list[ChunkMetadata]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chunks (chunk_id, document_id, chunk, embedding) VALUES (%s, %s, %s::jsonb, %s) "
                "ON CONFLICT (chunk_id) DO UPDATE SET document_id = EXCLUDED.document_id, chunk = EXCLUDED.chunk, "
                "embedding = EXCLUDED.embedding",
                [(chunk.chunk_id, chunk.document_id, chunk.model_dump_json(), self.embedder.embed(chunk.text))
                 for chunk in chunks],
            )

    def _patch(self, document_id: str, fields: dict) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE chunks SET chunk = chunk || %s::jsonb WHERE document_id = %s",
                               (json.dumps(fields), document_id))

    def mark_document_current(self, document_id: str) -> None:
        self._patch(document_id, {"is_current": True, "valid_to": None})

    def mark_document_not_current(self, document_id: str, valid_to: str) -> None:
        self._patch(document_id, {"is_current": False, "valid_to": valid_to})

    def set_in_force(self, document_id: str, start: date | None, end: date | None) -> None:
        self._patch(document_id, {"in_force_from": start.isoformat() if start else None,
                                  "in_force_to": end.isoformat() if end else None})

    def apply_lifecycle(self, document_id: str, lifecycle: str) -> None:
        self._patch(document_id, {"lifecycle": lifecycle, "authority_current": lifecycle in {"ACTIVE", "AMENDED"}})

    def remove_document_ids(self, document_ids: set[str]) -> None:
        if document_ids:
            with self._connect() as connection:
                connection.execute("DELETE FROM chunks WHERE document_id = ANY(%s)", (list(document_ids),))


def open_vector_store(settings) -> LocalVectorStore:
    """The chunk index selected by VECTOR_BACKEND: "filesystem" (default) or "postgres" (DATABASE_URL)."""
    if settings.vector_backend == "postgres":
        if not settings.database_url:
            raise ValueError("VECTOR_BACKEND=postgres requires DATABASE_URL.")
        return PostgresVectorStore(settings.database_url)
    return LocalVectorStore(settings.runtime_dir / "vectors.json")
