"""Successor linking and switch-over, end to end.

The successor is the real Digital Lending Directions, 2025 text (header and repeal section),
with one synthetic change: its commencement clause says the whole Directions take effect on
1 November 2025. (The real clause makes them effective immediately, except paragraphs 6 and
17.) That lets these tests cover a successor issued before it takes effect. The documents it
replaces or cites are synthetic pages in RBI's header format.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app import clock
from app.config.settings import Settings
from app.ingestion.service import IngestionService, OfficialStatusError
from app.models.documents import DocumentLifecycle
from app.models.links import LinkTrust
from app.monitoring.linking import LinkingService
from app.monitoring.metadata import extract_rbi_document_facts

FIXTURES = Path(__file__).parent / "fixtures" / "rbi_headers"
OLD_URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382&Mode=0"
NEW_URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0"
KFS_URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12663&Mode=0"

OLD_TEXT = """Notifications
 (500 kb)
Guidelines on Digital Lending
RBI/2022-23/111
 DOR.CRE.REC.66/21.07.001/2022-23
September 02, 2022
All Commercial Banks
Regulated entities shall disburse digital loans directly into the bank account of the borrower.
"""
KFS_TEXT = """Notifications
 (300 kb)
Key Facts Statement (KFS) for Loans & Advances
RBI/2024-25/18
 DOR.STR.REC.13/13.03.00/2024-25
April 15, 2024
Regulated entities shall provide a Key Facts Statement to borrowers.
"""


def at(day: date):
    return clock.simulated(lambda: datetime(day.year, day.month, day.day, 9, tzinfo=UTC))


REAL_COMMENCEMENT = ("ii. These Directions shall come into force immediately except for para 6, which shall come into "
                     "effect from November 1, 2025, and para 17, which shall come into effect from June 15, 2025.")


def new_text() -> str:
    header = (FIXTURES / "digital_lending_directions_2025.txt").read_text(encoding="utf-8")
    assert REAL_COMMENCEMENT in header
    header = header.replace(REAL_COMMENCEMENT, "ii. These Directions shall come into effect from November 1, 2025.")
    return header + \
        (FIXTURES / "digital_lending_repeal_section.txt").read_text(encoding="utf-8") + \
        "\nDigital loans shall be disbursed directly into the bank account of the borrower under these Directions.\n"


def add(service: IngestionService, url: str, text: str, title: str, lifecycle: DocumentLifecycle, method: str = "CURATED_APPROVAL"):
    document = service.ingest_content(text.encode("utf-8"), url, "page.txt", title).document
    service.apply_monitoring_metadata(url, extract_rbi_document_facts(text), clock.now())
    service.set_lifecycle(document.document_id, lifecycle, url, "Fixture status evidence for the test.", clock.now(), method)
    return service.get(document.document_id)


@pytest.fixture
def corpus(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    service = IngestionService(settings)
    with at(date(2025, 6, 1)):
        old = add(service, OLD_URL, OLD_TEXT, "Guidelines on Digital Lending", DocumentLifecycle.ACTIVE)
        kfs = add(service, KFS_URL, KFS_TEXT, "Key Facts Statement", DocumentLifecycle.ACTIVE)
        new = add(service, NEW_URL, new_text(), "Digital Lending Directions, 2025", DocumentLifecycle.REVIEW_REQUIRED, "AUTOMATED")
    return settings, service, old, kfs, new


def current_answers(service: IngestionService, day: date) -> set[str]:
    with at(day):
        return {item.document_id for item in service.vector_store.search("digital loans bank account borrower", top_k=10)}


def test_an_explicit_repeal_is_trusted_and_the_old_rule_ends_on_the_new_effective_date(corpus) -> None:
    settings, service, old, kfs, new = corpus

    with at(date(2025, 6, 2)):
        summary = LinkingService(service, settings).reconcile()

    (link,) = LinkingService(service, settings).store.all()
    assert (link.old_document_id, link.new_document_id, link.trust) == (old.document_id, new.document_id, LinkTrust.AUTO_TRUSTED)
    assert "RBI/2022-23/111" in link.evidence_quote and summary.auto_trusted == 1
    assert service.get(new.document_id).lifecycle is DocumentLifecycle.ACTIVE
    assert service.get(new.document_id).status_resolution_method == "AUTO_SUCCESSOR"
    assert service.get(old.document_id).in_force_to == date(2025, 11, 1)
    # Issued 8 May 2025 but effective 1 November 2025: the old rule answers until then.
    assert service.get(old.document_id).lifecycle is DocumentLifecycle.ACTIVE
    pair = {old.document_id, new.document_id}
    assert current_answers(service, date(2025, 10, 31)) & pair == {old.document_id}
    assert current_answers(service, date(2025, 11, 1)) & pair == {new.document_id}
    assert kfs.document_id in current_answers(service, date(2025, 11, 1))  # the cited rule is unaffected


def test_the_old_document_is_marked_superseded_once_the_day_arrives_and_kept_for_history(corpus) -> None:
    settings, service, old, kfs, new = corpus
    linking = LinkingService(service, settings)
    with at(date(2025, 6, 2)):
        linking.reconcile()

    with at(date(2025, 11, 2)):
        linking.reconcile()

    stored = service.get(old.document_id)
    assert stored.lifecycle is DocumentLifecycle.SUPERSEDED and stored.is_current is False
    assert stored.successor_document_id == new.document_id
    assert service.vector_store.get_by_document_id(old.document_id)  # history is kept
    edges = [data for _, _, data in service.graph_service.store.graph.edges(data=True) if data.get("relationship_type") == "SUPERSEDES"]
    assert len(edges) == 1 and "RBI/2022-23/111" in edges[0]["evidence_quote"]


def test_a_circular_the_successor_only_cites_is_never_linked(corpus) -> None:
    settings, service, old, kfs, new = corpus

    with at(date(2025, 6, 2)):
        LinkingService(service, settings).reconcile()

    assert not LinkingService(service, settings).store.for_old(kfs.document_id)
    assert service.get(kfs.document_id).lifecycle is DocumentLifecycle.ACTIVE


def test_reconciling_again_changes_nothing(corpus) -> None:
    settings, service, old, kfs, new = corpus
    linking = LinkingService(service, settings)
    with at(date(2025, 11, 2)):
        linking.reconcile()
        again = linking.reconcile()

    assert (again.links_created, again.switches_applied) == (0, 0)


def test_with_auto_trust_off_the_link_waits_and_approval_applies_it(corpus) -> None:
    settings, service, old, kfs, new = corpus
    linking = LinkingService(service, settings.model_copy(update={"auto_trust_enabled": False}))
    with at(date(2025, 11, 2)):
        linking.reconcile()
        (link,) = linking.store.pending_review()
        assert service.get(old.document_id).lifecycle is DocumentLifecycle.ACTIVE
        assert "switched off" in " ".join(link.trust_reasons)

        linking.approve(link.link_id, NEW_URL, "Annex III of the Directions lists this circular as repealed.")

    assert service.get(old.document_id).lifecycle is DocumentLifecycle.SUPERSEDED
    assert service.get(old.document_id).status_resolution_method == "ADMIN_REVIEW"


def test_rejecting_a_trusted_link_undoes_the_switch_without_adding_trust(corpus) -> None:
    settings, service, old, kfs, new = corpus
    linking = LinkingService(service, settings)
    with at(date(2025, 11, 2)):
        linking.reconcile()
        (link,) = linking.store.all()

        linking.reject(link.link_id)
        linking.reconcile()  # the rejected link is not re-trusted

    stored_old, stored_new = service.get(old.document_id), service.get(new.document_id)
    assert stored_old.lifecycle is DocumentLifecycle.REVIEW_REQUIRED and stored_old.is_current and stored_old.in_force_to is None
    assert stored_new.lifecycle is DocumentLifecycle.REVIEW_REQUIRED
    assert linking.store.get(link.link_id).trust is LinkTrust.REJECTED
    assert not [d for _, _, d in service.graph_service.store.graph.edges(data=True) if d.get("relationship_type") == "SUPERSEDES"]


def test_a_successor_rbi_has_withdrawn_cannot_be_approved(corpus) -> None:
    settings, service, old, kfs, new = corpus
    linking = LinkingService(service, settings.model_copy(update={"auto_trust_enabled": False}))
    with at(date(2025, 6, 2)):
        linking.reconcile()
    service.set_lifecycle(new.document_id, DocumentLifecycle.WITHDRAWN, NEW_URL, "Withdrawn watermark", clock.now(), "AUTOMATED")
    (link,) = linking.store.all()

    with pytest.raises(OfficialStatusError):
        linking.approve(link.link_id, NEW_URL, "Reviewer tries to approve a withdrawn successor anyway.")


def test_a_routine_check_of_the_old_page_does_not_undo_the_switch(corpus) -> None:
    from app.models.monitoring import DiscoveredDocument, RegulatorySource, SourceType
    from app.monitoring.fetcher import SourceFetcher
    from app.monitoring.lifecycle import LifecycleResolution
    from app.monitoring.processor import MonitoringDocumentProcessor
    from app.monitoring.service import RegulatoryMonitor
    from app.monitoring.store import MonitoringStore

    settings, service, old, kfs, new = corpus
    with at(date(2025, 11, 2)):
        LinkingService(service, settings).reconcile()

    class OldPage(SourceFetcher):
        def discover(self, source):
            return [DiscoveredDocument(canonical_url=OLD_URL, title="Guidelines on Digital Lending", metadata_hash="x")]

        def download_text(self, document):
            return OLD_TEXT

        def lifecycle_resolution(self, document):
            return LifecycleResolution(DocumentLifecycle.REVIEW_REQUIRED, "No watermark", clock.now())

    source = RegulatorySource(source_id="old", source_name="Old", url=OLD_URL, source_type=SourceType.DOCUMENT,
                              regulatory_topics=["digital lending"], parser_strategy="rbi_document",
                              approved_lifecycle=DocumentLifecycle.ACTIVE)
    store = MonitoringStore(settings.runtime_dir / "monitoring.json")
    with at(date(2025, 11, 3)):
        for _ in range(2):
            RegulatoryMonitor(store, OldPage(), MonitoringDocumentProcessor(service)).check_source(source)

    assert service.get(old.document_id).lifecycle is DocumentLifecycle.SUPERSEDED


def test_review_endpoints_require_the_admin_key_and_apply_a_decision(corpus, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.config.settings import get_settings
    from app.main import create_app

    settings, service, old, kfs, new = corpus
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("ADMIN_API_KEY", "key")
    monkeypatch.setenv("AUTO_TRUST_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())
    with at(date(2025, 11, 2)):
        LinkingService(service, settings.model_copy(update={"auto_trust_enabled": False})).reconcile()

        assert client.get("/admin/links/review-queue").status_code == 401
        (pending,) = client.get("/admin/links/review-queue", headers={"X-Admin-Key": "key"}).json()
        body = {"evidence_url": NEW_URL, "evidence_excerpt": "Annex III of the Directions lists this circular as repealed."}
        assert client.post("/admin/links/link_missing/approve", headers={"X-Admin-Key": "key"}, json=body).status_code == 404
        approved = client.post(f"/admin/links/{pending['link_id']}/approve", headers={"X-Admin-Key": "key"}, json=body)

    assert approved.status_code == 200 and approved.json()["trust"] == "APPROVED"
    assert [item["trust"] for item in client.get("/document-links").json()] == ["APPROVED"]
    assert IngestionService(settings).get(old.document_id).lifecycle is DocumentLifecycle.SUPERSEDED


def test_a_withdrawn_rule_with_no_stated_successor_gets_a_reviewable_current_candidate(corpus) -> None:
    settings, service, old, kfs, new = corpus
    with at(date(2025, 6, 2)):
        service.set_lifecycle(kfs.document_id, DocumentLifecycle.WITHDRAWN, KFS_URL, "Withdrawn watermark", clock.now(), "AUTOMATED")
        LinkingService(service, settings).reconcile()

    (candidate,) = LinkingService(service, settings).store.for_old(kfs.document_id)
    assert candidate.new_document_id == new.document_id and candidate.trust is LinkTrust.REVIEW_REQUIRED
    assert candidate.method == "candidate_content_match"
    assert "Key Fact" in candidate.evidence_quote  # the matching passage of the new document, quoted


def test_a_withdrawn_document_is_never_suggested_as_a_replacement(corpus) -> None:
    settings, service, old, kfs, new = corpus
    with at(date(2025, 6, 2)):
        for document in (kfs, new):
            service.set_lifecycle(document.document_id, DocumentLifecycle.WITHDRAWN, KFS_URL, "Withdrawn watermark",
                                  clock.now(), "AUTOMATED")
        LinkingService(service, settings).reconcile()

    assert LinkingService(service, settings).store.for_old(kfs.document_id) == []
