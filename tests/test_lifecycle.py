from app.models.documents import DocumentLifecycle
from app.monitoring.lifecycle import resolve_lifecycle


def test_official_withdrawn_marker_is_detected() -> None:
    result = resolve_lifecycle("Master Circular - Prudential Norms on Advances. Withdrawn")

    assert result.lifecycle is DocumentLifecycle.WITHDRAWN
    assert "Withdrawn" in result.excerpt


def test_absence_of_a_lifecycle_marker_is_not_treated_as_active() -> None:
    result = resolve_lifecycle("RBI circular dated April 1, 2025 is available on this page.")

    assert result.lifecycle is DocumentLifecycle.REVIEW_REQUIRED
