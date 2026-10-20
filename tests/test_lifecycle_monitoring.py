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

    def __call__(self, document, text, version, raw_html=None):
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


def test_lifecycle_transition_creates_a_real_monitoring_event(tmp_path: Path) -> None:
    source = RegulatorySource(
        source_id="irac", source_name="IRAC", url="https://rbi.org.in/irac",
        source_type=SourceType.DOCUMENT, regulatory_topics=["advances"], parser_strategy="rbi_document",
    )
    store = MonitoringStore(tmp_path / "monitor.json")
    RegulatoryMonitor(store, ReviewRequiredFetcher(), RecordingProcessor()).check_source(source)

    check, updates = RegulatoryMonitor(store, WatermarkedFetcher(), RecordingProcessor()).check_source(source)

    assert check.status.value == "CHANGES_DETECTED"
    assert len(updates) == 1
    assert updates[0].change_type.value == "LIFECYCLE_CHANGED"
    assert store.versions()[0].lifecycle is DocumentLifecycle.WITHDRAWN


def test_a_routine_check_does_not_undo_a_reviewer_approval(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from app.config.settings import Settings
    from app.ingestion.service import IngestionService
    from app.monitoring.processor import MonitoringDocumentProcessor

    ingestion = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    processor = MonitoringDocumentProcessor(ingestion)
    source = RegulatorySource(source_id="irac", source_name="IRAC", url="https://rbi.org.in/irac",
                              source_type=SourceType.DOCUMENT, regulatory_topics=["advances"], parser_strategy="rbi_document")
    store = MonitoringStore(tmp_path / "monitor.json")
    RegulatoryMonitor(store, ReviewRequiredFetcher(), processor).check_source(source)
    document = ingestion.manifest.get_by_source_url("https://rbi.org.in/irac")
    ingestion.approve_lifecycle(document.document_id, DocumentLifecycle.ACTIVE, "https://rbi.org.in/irac",
                                "Reviewer confirmed the circular is operative on the RBI page.", datetime.now(UTC))

    _, first = RegulatoryMonitor(store, ReviewRequiredFetcher(), processor).check_source(source)
    _, later = RegulatoryMonitor(store, ReviewRequiredFetcher(), processor).check_source(source)

    assert ingestion.manifest.get_by_source_url("https://rbi.org.in/irac").lifecycle is DocumentLifecycle.ACTIVE
    # One honest event records the approval; routine checks after it add nothing.
    assert [item.summary for item in first] == [
        "Status changed from review required to active after a reviewer's approval; the RBI page itself did not change."
    ]
    assert later == []


def test_an_rbi_withdrawal_still_overrides_a_reviewer_approval(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from app.config.settings import Settings
    from app.ingestion.service import IngestionService
    from app.monitoring.processor import MonitoringDocumentProcessor

    ingestion = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    processor = MonitoringDocumentProcessor(ingestion)
    source = RegulatorySource(source_id="irac", source_name="IRAC", url="https://rbi.org.in/irac",
                              source_type=SourceType.DOCUMENT, regulatory_topics=["advances"], parser_strategy="rbi_document")
    store = MonitoringStore(tmp_path / "monitor.json")
    RegulatoryMonitor(store, ReviewRequiredFetcher(), processor).check_source(source)
    document = ingestion.manifest.get_by_source_url("https://rbi.org.in/irac")
    ingestion.approve_lifecycle(document.document_id, DocumentLifecycle.ACTIVE, "https://rbi.org.in/irac",
                                "Reviewer confirmed the circular is operative on the RBI page.", datetime.now(UTC))

    RegulatoryMonitor(store, WatermarkedFetcher(), processor).check_source(source)

    assert ingestion.manifest.get_by_source_url("https://rbi.org.in/irac").lifecycle is DocumentLifecycle.WITHDRAWN
