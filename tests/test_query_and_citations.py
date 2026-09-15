from pathlib import Path

from app.config.settings import Settings
from app.ingestion.service import IngestionService
from app.llm.citations import validate_citations
from app.llm.generation import GenerationResult, deterministic_research
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
    assert response.research is not None
    assert response.research.direct_answer is not None
    assert set(response.research.direct_answer.citation_ids).issubset({citation.chunk_id for citation in response.citations})


def test_query_explains_the_rbi_lending_scope_for_unrelated_question(tmp_path: Path) -> None:
    response = RegulatoryQueryService(Settings(data_dir=tmp_path / "data")).query("What is the weather in Mumbai?")

    assert not response.in_scope
    assert not response.retrieved_evidence
    assert not response.citations
    assert "RBI lending guidelines" in response.answer


def test_query_returns_a_clear_insufficient_evidence_state(tmp_path: Path) -> None:
    response = RegulatoryQueryService(Settings(data_dir=tmp_path / "data")).query("Can an NBFC charge foreclosure fees?")

    assert response.research is not None
    assert response.research.status.value == "insufficient_evidence"
    assert response.research.direct_answer is not None
    assert response.citation_valid


def test_query_falls_back_to_cited_evidence_when_model_citation_is_invalid(tmp_path: Path) -> None:
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India states that lenders must disclose penal charges clearly.")
    settings = Settings(data_dir=tmp_path / "data")
    IngestionService(settings).ingest(IngestRequest(local_path=str(source), title="RBI Penal Charges Direction"))
    service = RegulatoryQueryService(settings)

    class InvalidCitationGenerator:
        def generate(self, query, evidence):
            return GenerationResult(answer="Unverified statement [chunk_00000000000000000000]", model="test")

    service.generator = InvalidCitationGenerator()
    response = service.query("What must lenders disclose about penal charges?")

    assert response.citation_valid
    assert response.citations
    assert "RBI Penal Charges Direction states" in response.answer


def test_deterministic_research_selects_the_consent_provision_not_page_chrome() -> None:
    chunk = ChunkMetadata(
        chunk_id="chunk_consent",
        document_id="digital_lending",
        document_title="RBI Digital Lending Directions, 2025",
        page_number=1,
        chunk_index=0,
        text=(
            "Notifications | Official Website of Reserve Bank of India. "
            "RE shall ensure that any collection of data by their DLA and DLA of their LSP is need-based "
            "and with prior and explicit consent of the borrower having audit trail. "
            "The borrower shall be provided with an option to give or deny consent for use of specific data."
        ),
    )

    research = deterministic_research("What consent is required in digital lending?", [chunk])

    assert research.direct_answer is not None
    assert "prior and explicit consent" in research.direct_answer.text
    assert "Notifications |" not in research.direct_answer.text
