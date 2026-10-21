"""RBI's register of withdrawn circulars. The fixture rows are real (21 October 2026)."""

from datetime import UTC, date, datetime
from pathlib import Path

from app.config.settings import Settings
from app.ingestion.service import IngestionService
from app.models.documents import DocumentLifecycle
from app.monitoring.withdrawn_register import REGISTER_URL, apply_register, parse_register, select_predecessors

PAGE = (Path(__file__).parent / "fixtures" / "rbi_withdrawn_register.html").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)


def test_numbered_rows_are_read_from_both_departments_only() -> None:
    entries = parse_register(PAGE)

    assert [entry.section for entry in entries] == ["Circulars Withdrawn by the Department of Regulation"] * 3 + [
        "Circulars Withdrawn by the Department of Supervision"]
    penal = entries[0]
    assert penal.keys == ("DOR.MCS.REC.28/01.01.001/2023-24",)
    assert penal.title == "Fair Lending Practice - Penal Charges in Loan Accounts"
    assert penal.issued == date(2023, 8, 18)
    assert penal.page_url and "NotificationUser.aspx" in penal.page_url
    assert entries[3].title == "Fair Practices Code for Lenders - Charging of Interest"


def _service(tmp_path: Path) -> IngestionService:
    return IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))


def _add(service: IngestionService, url: str, numbers: list[str], lifecycle=DocumentLifecycle.ACTIVE):
    document = service.ingest_content(f"Text of {url}".encode(), url, "page.txt", url).document
    service.manifest.set_fields(document.document_id, circular_numbers=numbers)
    service.set_lifecycle(document.document_id, lifecycle, url, "Fixture status evidence.", NOW, "CURATED_APPROVAL")
    return document.document_id


def test_a_listed_document_is_withdrawn_with_the_register_row_as_evidence(tmp_path) -> None:
    service = _service(tmp_path)
    penal = _add(service, "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12527&Mode=0",
                 ["RBI/2023-24/53", "DOR.MCS.REC.28/01.01.001/2023-24"])
    unrelated = _add(service, "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=1&Mode=0", ["RBI/2025-26/1"])

    assert apply_register(service, parse_register(PAGE), NOW) == [penal]

    stored = service.get(penal)
    assert stored.lifecycle is DocumentLifecycle.WITHDRAWN and stored.status_evidence_url == REGISTER_URL
    assert "Fair Lending Practice - Penal Charges in Loan Accounts" in stored.status_evidence_excerpt
    assert penal not in {item.document_id for item in service.vector_store.search("penal", top_k=5)}  # out of current answers
    assert service.get(unrelated).lifecycle is DocumentLifecycle.ACTIVE


def test_a_document_without_parsed_numbers_is_matched_by_its_rbi_address(tmp_path) -> None:
    service = _service(tmp_path)
    penal = _add(service, "https://rbi.org.in/scripts/NotificationUser.aspx?Mode=0&Id=12527", [])

    assert apply_register(service, parse_register(PAGE), NOW) == [penal]


def test_a_superseded_document_keeps_its_successor_evidence(tmp_path) -> None:
    service = _service(tmp_path)
    penal = _add(service, "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12527&Mode=0",
                 ["DOR.MCS.REC.28/01.01.001/2023-24"], DocumentLifecycle.SUPERSEDED)

    assert apply_register(service, parse_register(PAGE), NOW) == []
    assert service.get(penal).lifecycle is DocumentLifecycle.SUPERSEDED


def test_a_routine_page_check_does_not_undo_a_register_withdrawal(tmp_path) -> None:
    from app.models.monitoring import DiscoveredDocument
    from app.monitoring.lifecycle import LifecycleResolution
    from app.monitoring.processor import MonitoringDocumentProcessor

    url = "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12527&Mode=0"
    service = _service(tmp_path)
    penal = _add(service, url, ["DOR.MCS.REC.28/01.01.001/2023-24"])
    apply_register(service, parse_register(PAGE), NOW)

    # The page shows no watermark, and the source is a curated approval: neither may restore it.
    MonitoringDocumentProcessor(service).assess_lifecycle(
        DiscoveredDocument(canonical_url=url, title="Penal charges", metadata_hash="x"), "Text",
        LifecycleResolution(DocumentLifecycle.ACTIVE, "Curated approval", NOW, "CURATED_APPROVAL"),
    )

    assert service.get(penal).lifecycle is DocumentLifecycle.WITHDRAWN


def test_predecessors_follow_the_written_rule_with_a_reason_each() -> None:
    import yaml

    rule = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "corpus" / "inclusion.yaml")
                          .read_text(encoding="utf-8"))["withdrawn_circulars"]
    decisions = {entry.title: (included, reason) for entry, included, reason in select_predecessors(parse_register(PAGE), rule)}

    assert decisions["Fair Lending Practice - Penal Charges in Loan Accounts"] == (True, "lending topic 'loan'")
    assert decisions["Guidelines on Digital Lending"][0] is True
    assert all(reason.startswith(("lending topic", "issued before", "title names", "register gives")) for _, reason in decisions.values())


def test_a_listed_rule_issued_before_the_consolidation_ended_on_28_november_2025(tmp_path) -> None:
    from app import clock

    service = _service(tmp_path)
    penal = _add(service, "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12527&Mode=0",
                 ["DOR.MCS.REC.28/01.01.001/2023-24"])
    service.manifest.set_fields(penal, publication_date=date(2023, 8, 18))
    service.set_in_force(penal, date(2024, 1, 1), None)

    with clock.simulated(lambda: NOW):
        apply_register(service, parse_register(PAGE), NOW)
        assert service.get(penal).in_force_to == date(2025, 11, 28)  # not the day we noticed it

        def found(day):
            return penal in {item.document_id for item in service.vector_store.search("penal", top_k=5, as_of=day)}

        assert found(date(2025, 6, 1))  # the rule in force then, although withdrawn since
        assert not found(date(2023, 12, 1)) and not found(date(2025, 11, 28)) and not found(NOW.date())


def test_the_register_never_reopens_a_window_a_successor_closed_sooner(tmp_path) -> None:
    service = _service(tmp_path)
    penal = _add(service, "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12527&Mode=0",
                 ["DOR.MCS.REC.28/01.01.001/2023-24"], DocumentLifecycle.SUPERSEDED)
    service.manifest.set_fields(penal, publication_date=date(2023, 8, 18))
    service.set_in_force(penal, date(2024, 1, 1), date(2025, 5, 8))

    apply_register(service, parse_register(PAGE), NOW)

    assert service.get(penal).in_force_to == date(2025, 5, 8)


def test_a_withdrawal_without_a_known_end_closes_the_window_when_it_was_seen(tmp_path) -> None:
    service = _service(tmp_path)
    rule = _add(service, "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=1&Mode=0", ["RBI/2025-26/1"])

    service.set_lifecycle(rule, DocumentLifecycle.WITHDRAWN, "https://www.rbi.org.in/x", "Withdrawn watermark.", NOW, "RBI_WATERMARK")

    assert service.get(rule).in_force_to == NOW.date()


def test_a_rule_whose_status_was_never_settled_is_not_answered_from_on_any_date(tmp_path) -> None:
    from app import clock

    service = _service(tmp_path)
    rule = _add(service, "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=1&Mode=0", ["RBI/2025-26/1"],
                DocumentLifecycle.REVIEW_REQUIRED)

    with clock.simulated(lambda: NOW):
        assert rule not in {item.document_id for item in service.vector_store.search("Text", top_k=5, as_of=date(2025, 6, 1))}
