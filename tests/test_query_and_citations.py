from pathlib import Path

from app.config.settings import Settings
from app.ingestion.service import IngestionService
from app.llm.citations import validate_citations
from app.models.chunks import ChunkMetadata
from app.models.documents import IngestRequest
from app.retrieval.query_service import RegulatoryQueryService


def test_citation_validator_rejects_unknown_chunk() -> None:
    evidence = [ChunkMetadata(chunk_id="chunk_aaaaaaaaaaaaaaaaaaaa", document_id="doc_a", document_title="A", page_number=1, chunk_index=0, text="evidence")]
    assert validate_citations("A claim [chunk_aaaaaaaaaaaaaaaaaaaa]", evidence)
    assert not validate_citations("A claim [chunk_bbbbbbbbbbbbbbbbbbbb]", evidence)


def test_query_returns_only_verifiable_evidence(tmp_path: Path) -> None:
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India states that lenders must disclose penal charges clearly.")
    settings = Settings(data_dir=tmp_path / "data")
    IngestionService(settings).ingest(IngestRequest(local_path=str(source), title="RBI Penal Charges Direction"))

    response = RegulatoryQueryService(settings).query("What must lenders disclose about penal charges?")

    assert response.citation_valid
    assert response.citations
    assert all(citation.chunk_id in response.answer for citation in response.citations)
    assert response.estimated_cost_usd == 0.0

