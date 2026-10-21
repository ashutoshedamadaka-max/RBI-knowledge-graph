"""The three Phase 2 chunkers. Real-document tests use the committed NBFC Responsible Business Conduct PDF."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ingestion.chunkers import CHUNKERS, STRUCTURE_MAX, chunk_structure, count_tokens, segment
from app.ingestion.parser import parse_document
from app.models.documents import DocumentMetadata

RBC_PDF = Path(__file__).resolve().parents[1] / "data" / "source_pdfs" / "362MD26CA543937BA439A97E1BCFC08CF5808.PDF"


def _document(document_id: str = "doc_test") -> DocumentMetadata:
    return DocumentMetadata(document_id=document_id, title="Test direction", content_hash="x", file_name="x.pdf",
                            mime_type="application/pdf", ingested_at=datetime.now(UTC))


@pytest.fixture(scope="module")
def rbc_pages() -> list[str]:
    return parse_document(RBC_PDF, "application/pdf").pages


def test_numbered_paragraphs_are_found_in_order_under_their_headings(rbc_pages) -> None:
    units = segment(rbc_pages)
    numbers = [int(unit.label) for unit in units if unit.label.isdigit()]

    assert numbers[:109] == list(range(1, 110))  # paragraphs 1 to 109, none skipped
    seventh = next(unit for unit in units if unit.label == "7")
    assert seventh.heading_path == ("Chapter II – Institutional Framework", "A. Role of Board")
    assert not any("....." in heading for unit in units for heading in unit.heading_path)  # contents lines are not headings


@pytest.mark.parametrize("name", list(CHUNKERS))
def test_every_chunker_gives_stable_unique_ids_within_its_size_limit(rbc_pages, name) -> None:
    first = CHUNKERS[name](_document(), rbc_pages)
    again = CHUNKERS[name](_document(), rbc_pages)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in again]
    assert len({chunk.chunk_id for chunk in first}) == len(first)
    assert max(chunk.token_count for chunk in first) <= {"fixed": 510, "recursive": 540, "structure": STRUCTURE_MAX}[name]
    assert all(chunk.chunker == name for chunk in first)


def test_a_structure_chunk_carries_its_paragraph_heading_and_parent(rbc_pages) -> None:
    chunks = chunk_structure(_document(), rbc_pages)
    seventh = next(chunk for chunk in chunks if chunk.paragraph_ref and chunk.paragraph_ref.split("–")[0] == "7")

    assert seventh.text.startswith("[Chapter II – Institutional Framework > A. Role of Board]\n7. ")
    assert seventh.heading_path == "Chapter II – Institutional Framework > A. Role of Board"
    assert seventh.page_number == 7 and seventh.parent_id
    assert seventh.token_count == count_tokens(seventh.text)


def test_a_contents_page_without_dot_leaders_is_not_read_as_headings() -> None:
    # The layout of a real Master Circular: numbered contents, then an annex list, then the body.
    text = ("Master Circular - Prudential norms\nTable of Contents\nPart A\n1. GENERAL\n2. DEFINITIONS\n"
            "Annex – 5: List of Circulars consolidated by the Master Circular on IRAC Norms\n"
            "1. GENERAL\n1.1 Banks are required to classify assets on their record of recovery.\n"
            "2. DEFINITIONS\n2.1 A non-performing asset is a loan for which interest is overdue.\n")

    units = segment([text])

    assert units[1].label == "contents" and "Annex – 5" in " ".join(units[1].lines)
    body = [unit for unit in units if unit.label in {"1", "2"}]
    assert [unit.label for unit in body] == ["1", "2"] and all(unit.heading_path == () for unit in body)


def test_a_table_stays_whole_when_it_fits_and_repeats_its_caption_when_it_does_not() -> None:
    small = ["1. The repayment schedule is set out below:", "Schedule of instalments"] + \
        [cell for row in range(1, 4) for cell in (str(row), "20,000", "720", "970")]
    (chunk,) = chunk_structure(_document(), ["\n".join(small)])
    assert "Schedule of instalments" in chunk.text and "970" in chunk.text

    big = ["1. Circulars repealed are listed below:", "List of circulars repealed"] + \
        [cell for row in range(1, 400) for cell in (f"{row}.", f"DOR.CRE.REC.{row}/21.07.001/2022-23", "02.09.2022")]
    parts = chunk_structure(_document(), ["\n".join(big)])
    assert len(parts) > 1 and all(chunk.token_count <= STRUCTURE_MAX for chunk in parts)
    assert all("List of circulars repealed" in chunk.text for chunk in parts[1:])


def test_ingestion_uses_the_configured_chunker(tmp_path) -> None:
    from app.config.settings import Settings
    from app.ingestion.service import IngestionService

    text = b"1. Lenders must disclose penal charges in the Key Facts Statement.\n2. Penal charges must be reasonable.\n"
    legacy = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "a")).ingest_content(text, "https://rbi.org.in/a", "a.txt", "A").document
    structure = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "b", chunker="structure"))
    document = structure.ingest_content(text, "https://rbi.org.in/a", "a.txt", "A").document

    assert {chunk.chunker for chunk in structure.vector_store.get_by_document_id(document.document_id)} == {"structure"}
    assert legacy.document_id == document.document_id  # same document, chunked differently


# Enough words to keep each paragraph above the 100-token minimum, so they stay separate chunks.
FILLER = (" It shall be applied uniformly to all borrowers in the same category, without discrimination,"
          " and the policy shall be reviewed by the Board of the NBFC at least once in every financial year.") * 3


def test_the_answer_step_receives_the_whole_section_of_a_retrieved_paragraph(tmp_path) -> None:
    from unittest.mock import Mock, patch

    from app.llm.generation import OpenAIAnswerGenerator
    from app.retrieval.vector_store import LocalVectorStore

    text = ("Chapter III – Responsible Lending Conduct\nB. Penal Charges\n"
            "9. Penal charges, if any, shall be levied only for non-compliance with material terms of the loan "
            "contract and shall not be capitalised." + FILLER + "\n"
            "10. The quantum and reason for penal charges shall be clearly disclosed in the Key Facts Statement "
            "and loan agreement, and displayed on the NBFC's website." + FILLER + "\n"
            "C. Recovery\n11. Recovery agents shall not harass borrowers at odd hours.\n")
    chunks = chunk_structure(_document(), [text])
    store = LocalVectorStore(tmp_path / "vectors.json")
    store.upsert(chunks)
    ninth = next(chunk for chunk in chunks if chunk.paragraph_ref.startswith("9"))

    sections = store.sections([ninth])
    assert "10. The quantum and reason for penal charges" in sections[ninth.chunk_id]
    assert "Recovery agents" not in sections[ninth.chunk_id]  # a different section
    eleventh = next(chunk for chunk in chunks if chunk.paragraph_ref.startswith("11"))
    assert store.sections([eleventh]) == {}  # a one-paragraph section adds nothing

    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "{}"}}], "usage": {}}
    with patch("app.llm.generation.httpx.post", return_value=response) as post:
        OpenAIAnswerGenerator("k", "m", 0.15, 0.6, 12, 450).generate("Penal charges?", [ninth], sections)
    prompt = post.call_args.kwargs["json"]["messages"][1]["content"]
    assert "SECTION CONTEXT" in prompt and "10. The quantum and reason" in prompt and f"CHUNK {ninth.chunk_id}" in prompt
