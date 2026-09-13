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
