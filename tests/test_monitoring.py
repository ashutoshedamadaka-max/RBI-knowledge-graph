from pathlib import Path

from app.models.monitoring import DiscoveredDocument, RegulatorySource, SourceType
from app.monitoring.fetcher import SourceFetcher
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore
from app.monitoring.registry import RegulatorySourceRegistry


class FixtureFetcher(SourceFetcher):
    def __init__(self, text: str, unavailable: bool = False) -> None:
        self.text = text
        self.unavailable = unavailable
        self.document = DiscoveredDocument(
            canonical_url="https://www.rbi.org.in/example/penal-charges",
            title="Fair Lending Practice - Penal Charges in Loan Accounts",
            metadata_hash="fixture",
        )

    def discover(self, source: RegulatorySource) -> list[DiscoveredDocument]:
        if self.unavailable:
            raise RuntimeError("RBI source unavailable")
        return [self.document]

    def download_text(self, document: DiscoveredDocument) -> str:
        return self.text


def source() -> RegulatorySource:
    return RegulatorySource(
        source_id="fixture_rbi", source_name="Fixture RBI", url="https://www.rbi.org.in/",
        source_type=SourceType.NOTIFICATIONS, regulatory_topics=["penal charges"],
    )


def test_monitor_detects_new_unchanged_and_modified_without_duplicates(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path / "monitoring.json")
    first = RegulatoryMonitor(store, FixtureFetcher("Effective April 1, 2024. Penal charges must be disclosed."))
    check, updates = first.check_source(source())
    assert check.status.value == "CHANGES_DETECTED"
    assert len(updates) == 1
    assert len(store.versions()) == 1

    unchanged_check, unchanged_updates = first.check_source(source())
    assert unchanged_check.status.value == "NO_CHANGES"
    assert unchanged_updates == []
    assert len(store.versions()) == 1
    assert len(store.updates()) == 1

    changed = RegulatoryMonitor(store, FixtureFetcher("Effective April 1, 2025. Penal charges must be disclosed. NBFCs must provide a Key Fact Statement."))
    changed_check, changed_updates = changed.check_source(source())
    assert changed_check.status.value == "CHANGES_DETECTED"
    assert changed_updates[0].change_type.value == "MODIFIED"
    assert changed_updates[0].diff.changed_dates
    assert len(store.versions()) == 2
    assert store.versions()[0].is_current is False
    assert store.versions()[1].is_current is True


def test_unavailable_source_is_not_reported_as_no_changes(tmp_path: Path) -> None:
    check, updates = RegulatoryMonitor(MonitoringStore(tmp_path / "monitoring.json"), FixtureFetcher("", unavailable=True)).check_source(source())

    assert check.status.value == "SOURCE_UNAVAILABLE"
    assert updates == []


def test_curated_document_first_scan_establishes_a_baseline(tmp_path: Path) -> None:
    curated = source()
    curated.parser_strategy = "rbi_document"
    store = MonitoringStore(tmp_path / "monitoring.json")

    check, updates = RegulatoryMonitor(store, FixtureFetcher("RBI lending baseline")).check_source(curated)

    assert check.status.value == "NO_CHANGES"
    assert updates == []
    assert len(store.versions()) == 1


def test_curated_document_is_checked_even_when_listing_keywords_do_not_match(tmp_path: Path):
    curated = source().model_copy(update={"parser_strategy": "rbi_document", "regulatory_topics": ["unmatched topic"]})
    fetcher = FixtureFetcher("Official management of advances source.")
    fetcher.document.title = "Management of Advances"
    store = MonitoringStore(tmp_path / "monitoring.json")
    check, _ = RegulatoryMonitor(store, fetcher).check_source(curated)
    assert check.status.value == "NO_CHANGES"
    assert len(store.versions()) == 1


def test_monitor_ignores_case_and_whitespace_only_changes(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path / "monitoring.json")
    first = RegulatoryMonitor(store, FixtureFetcher("RBI lending rule: disclose penal charges."))
    first.check_source(source())

    check, updates = RegulatoryMonitor(store, FixtureFetcher("  rbi   LENDING RULE: disclose PENAL charges. ")).check_source(source())

    assert check.status.value == "NO_CHANGES"
    assert updates == []
    assert len(store.versions()) == 1


def test_clean_text_migration_resets_catalogue_history_once(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path / "monitoring.json")
    curated = source()
    curated.source_id = "rbi_curated"
    monitor = RegulatoryMonitor(store, FixtureFetcher("RBI lending rule."))
    monitor.check_source(curated)

    assert store.reset_catalogue_after_extraction_upgrade({"rbi_curated"}) == 1
    assert store.updates() == []
    assert store.checks() == []
    assert len(store.versions()) == 1
    assert store.reset_catalogue_after_extraction_upgrade({"rbi_curated"}) == 0


def test_official_registry_loads_only_rbi_sources() -> None:
    sources = RegulatorySourceRegistry(Path("config/regulatory_sources.yaml")).enabled_sources()

    assert sources
    assert all("rbi.org.in" in str(item.url) for item in sources)
    assert any(item.parser_strategy == "rbi_document" for item in sources)
    assert all(item.regulatory_topics for item in sources)
    assert {
        "rbi_digital_lending_directions",
        "rbi_colending_faqs",
        "rbi_property_document_release",
    }.issubset({item.source_id for item in sources})


def test_monitor_stamps_the_simulated_clock_during_a_replay(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from app import clock

    past = datetime(2023, 6, 1, 3, 0, tzinfo=UTC)
    store = MonitoringStore(tmp_path / "monitoring.json")
    with clock.simulated(lambda: past):
        check, _ = RegulatoryMonitor(store, FixtureFetcher("Penal charges must be disclosed.")).check_source(source())

    assert check.checked_at == past
    assert store.versions()[0].valid_from == past
    assert clock.now() > past  # real time is restored after the block


def test_monitored_page_is_stored_as_html_and_indexed_from_its_body(tmp_path: Path) -> None:
    from app.config.settings import Settings
    from app.ingestion.parser import extract_html_text
    from app.ingestion.service import IngestionService
    from app.monitoring.processor import MonitoringDocumentProcessor

    page = (
        "<html><body><nav>Skip to main content</nav><script>track()</script>"
        "<div id='NotificationUser'><p>RBI/2025-26/36</p><p>Lenders must disclose penal charges.</p>"
        "<p><s>Old wording that was deleted.</s></p></div></body></html>"
    )

    class HtmlFetcher(FixtureFetcher):
        def download_text(self, document):
            return extract_html_text(page)

        def raw_html(self, document):
            return page

    ingestion = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    store = MonitoringStore(tmp_path / "monitoring.json")
    RegulatoryMonitor(store, HtmlFetcher(""), MonitoringDocumentProcessor(ingestion)).check_source(source())

    document = ingestion.manifest.all()[0]
    assert document.mime_type == "text/html"
    assert (ingestion.settings.raw_dir / f"{document.document_id}.html").read_text(encoding="utf-8") == page
    indexed = " ".join(chunk.text for chunk in ingestion.vector_store.get_by_document_id(document.document_id))
    assert "Lenders must disclose penal charges." in indexed
    assert "track()" not in indexed and "Skip to main content" not in indexed and "Old wording" not in indexed
