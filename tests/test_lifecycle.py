from app.models.documents import DocumentLifecycle
from app.monitoring.lifecycle import resolve_lifecycle
from app.monitoring.metadata import extract_rbi_document_facts


def test_official_withdrawn_marker_is_detected() -> None:
    result = resolve_lifecycle("Master Circular - Prudential Norms on Advances. Withdrawn")

    assert result.lifecycle is DocumentLifecycle.WITHDRAWN
    assert "Withdrawn" in result.excerpt


def test_absence_of_a_lifecycle_marker_is_not_treated_as_active() -> None:
    result = resolve_lifecycle("RBI circular dated April 1, 2025 is available on this page.")

    assert result.lifecycle is DocumentLifecycle.REVIEW_REQUIRED


def test_rbi_metadata_is_extracted_only_when_published_in_the_source_text() -> None:
    facts = extract_rbi_document_facts(
        "RBI/2025-26/36. These Directions shall come into effect from November 1, 2025."
    )

    assert facts.document_identifier == "RBI/2025-26/36"
    assert str(facts.effective_date) == "2025-11-01"
