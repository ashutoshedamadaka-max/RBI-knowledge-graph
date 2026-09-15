from pathlib import Path

from app.models.documents import DocumentLifecycle
from app.models.monitoring import DiscoveredDocument, RegulatorySource, SourceType
from app.monitoring.fetcher import SourceFetcher
from app.monitoring.lifecycle import LifecycleResolution
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore


class WatermarkedFetcher(SourceFetcher):
    document = DiscoveredDocument(canonical_url="https://rbi.org.in/irac", title="IRAC advances", metadata_hash="irac")

    def discover(self, source):
        return [self.document]

    def download_text(self, document):
        return "IRAC advances"

    def lifecycle_resolution(self, document):
        from datetime import UTC, datetime
        return LifecycleResolution(DocumentLifecycle.WITHDRAWN, "Official RBI watermark", datetime.now(UTC))


class ReviewRequiredFetcher(WatermarkedFetcher):
    def lifecycle_resolution(self, document):
        from datetime import UTC, datetime
        return LifecycleResolution(DocumentLifecycle.REVIEW_REQUIRED, "No status watermark", datetime.now(UTC))


class RecordingProcessor:
    def __init__(self):
        self.created = False
        self.applied_after_create = False

    def __call__(self, document, text, version):
        self.created = True
        return "doc_latest", []

    def assess_lifecycle(self, document, text, resolution):
        self.applied_after_create = self.created
        return resolution


def test_changed_document_receives_lifecycle_after_new_version_is_created(tmp_path: Path) -> None:
    source = RegulatorySource(source_id="irac", source_name="IRAC", url="https://rbi.org.in/irac", source_type=SourceType.DOCUMENT, regulatory_topics=["advances"], parser_strategy="rbi_document")
    processor = RecordingProcessor()
    monitor = RegulatoryMonitor(MonitoringStore(tmp_path / "monitor.json"), WatermarkedFetcher(), processor)

    check, _ = monitor.check_source(source)

    assert check.status.value == "NO_CHANGES"  # curated first scan establishes its baseline
    assert processor.applied_after_create
    assert monitor.store.versions()[0].lifecycle is DocumentLifecycle.WITHDRAWN


def test_curated_approval_resolves_only_review_required_lifecycle(tmp_path: Path) -> None:
    source = RegulatorySource(
        source_id="approved_irac", source_name="IRAC", url="https://rbi.org.in/irac",
        source_type=SourceType.DOCUMENT, regulatory_topics=["advances"], parser_strategy="rbi_document",
        approved_lifecycle=DocumentLifecycle.ACTIVE,
        approval_evidence_excerpt="Official RBI source approved for current-guidance intake.",
    )
    processor = RecordingProcessor()
    monitor = RegulatoryMonitor(MonitoringStore(tmp_path / "monitor.json"), ReviewRequiredFetcher(), processor)

    monitor.check_source(source)

    assert monitor.store.versions()[0].lifecycle is DocumentLifecycle.ACTIVE


def test_withdrawn_marker_overrides_curated_approval(tmp_path: Path) -> None:
    source = RegulatorySource(
        source_id="approved_irac", source_name="IRAC", url="https://rbi.org.in/irac",
        source_type=SourceType.DOCUMENT, regulatory_topics=["advances"], parser_strategy="rbi_document",
        approved_lifecycle=DocumentLifecycle.ACTIVE,
    )
    monitor = RegulatoryMonitor(MonitoringStore(tmp_path / "monitor.json"), WatermarkedFetcher(), RecordingProcessor())

    monitor.check_source(source)

    assert monitor.store.versions()[0].lifecycle is DocumentLifecycle.WITHDRAWN
