from app.llm.citations import validate_structured_citations
from app.llm.generation import research_to_markdown
from app.models.chunks import ChunkMetadata
from app.models.research import ResearchClaim, ResearchSection, ResearchStatus, StructuredResearch


def test_long_structured_research_keeps_claims_separate_and_cited() -> None:
    evidence = [ChunkMetadata(
        chunk_id=f"chunk_{index:020x}", document_id="doc_long", document_title="RBI lending source",
        page_number=index + 1, chunk_index=index, text="Supporting RBI lending evidence.",
    ) for index in range(8)]
    claims = [ResearchClaim(text=("Requirement explanation. " * 18), citation_ids=[item.chunk_id]) for item in evidence]
    research = StructuredResearch(
        status=ResearchStatus.GROUNDED,
        direct_answer=ResearchClaim(text="A concise, source-backed conclusion.", citation_ids=[evidence[0].chunk_id]),
        sections=[ResearchSection(id="key-requirements", title="Key requirements", claims=claims)],
    )

    rendered = research_to_markdown(research)

    assert validate_structured_citations(research, evidence)
    assert rendered.count("- Requirement explanation") == 8
    assert len(rendered) > 1000


def test_structured_research_supports_scannable_display_metadata() -> None:
    evidence = [ChunkMetadata(
        chunk_id="chunk_00000000000000000001", document_id="doc_example", document_title="RBI Directions",
        page_number=1, chunk_index=0, text="Supporting evidence.",
    )]
    research = StructuredResearch(
        status=ResearchStatus.GROUNDED,
        display_title="Digital lending consent requirements",
        direct_answer=ResearchClaim(text="Prior consent is required.", citation_ids=[evidence[0].chunk_id]),
        sections=[ResearchSection(id="key-requirements", title="Key requirements", claims=[ResearchClaim(
            title="Borrowers control consent", text="Borrowers may revoke consent.", citation_ids=[evidence[0].chunk_id],
        )])],
    )

    assert research.display_title == "Digital lending consent requirements"
    assert research.sections[0].claims[0].title == "Borrowers control consent"
    assert validate_structured_citations(research, evidence)
