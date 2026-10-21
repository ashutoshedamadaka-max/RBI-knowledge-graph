"""What an answer says when the rule it matches was replaced, withdrawn or not yet in force."""

from datetime import date

from app.models.documents import DocumentLifecycle
from app.monitoring.linking import LinkingService
from app.retrieval.query_service import RegulatoryQueryService
from tests.test_linking import at, corpus  # noqa: F401  (pytest fixture)

QUESTION = "Must digital loans be disbursed directly into the bank account of the borrower?"


def ask(settings, day: date, as_of: date | None = None):
    with at(day):
        return RegulatoryQueryService(settings).query(QUESTION, as_of=as_of)


def link(settings, service, day: date) -> None:
    with at(day):
        LinkingService(service, settings).reconcile()


def test_after_the_switch_the_answer_names_the_replacement_and_never_cites_the_old_rule(corpus) -> None:
    settings, service, old, kfs, new = corpus
    link(settings, service, date(2025, 11, 2))

    response = ask(settings, date(2025, 11, 2))

    assert old.document_id not in {chunk.document_id for chunk in response.retrieved_evidence}
    assert new.document_id in {chunk.document_id for chunk in response.retrieved_evidence}
    (notice,) = [item for item in response.notices if item.kind == "replaced"]
    assert notice.text == (
        "Guidelines on Digital Lending was repealed by Digital Lending Directions, 2025, issued 8 May 2025, "
        "in force from 1 November 2025; this is the current rule."
    )
    assert "RBI/2022-23/111" in notice.evidence_excerpt
    assert response.answer.startswith("### What changed\n- Guidelines on Digital Lending was repealed")


def test_before_the_effective_date_the_answer_uses_the_old_rule_and_quotes_the_coming_one(corpus) -> None:
    settings, service, old, kfs, new = corpus
    link(settings, service, date(2025, 6, 2))

    response = ask(settings, date(2025, 10, 31))

    evidence = {chunk.document_id for chunk in response.retrieved_evidence}
    assert old.document_id in evidence and new.document_id not in evidence
    (notice,) = [item for item in response.notices if item.kind == "upcoming"]
    assert notice.text == (
        "Digital Lending Directions, 2025, issued 8 May 2025, takes effect from 1 November 2025. "
        "Until then, the rule in force is Guidelines on Digital Lending."
    )
    assert notice.evidence_chunk_id and notice.evidence_excerpt
    # The coming rule is quoted in the notice but never cited as current guidance.
    assert notice.evidence_chunk_id not in {item.chunk_id for item in response.citations}


def test_as_of_answers_from_the_rules_in_force_on_that_date(corpus) -> None:
    settings, service, old, kfs, new = corpus
    link(settings, service, date(2025, 6, 2))

    response = ask(settings, date(2025, 11, 2), as_of=date(2025, 10, 31))

    assert response.as_of == date(2025, 10, 31)
    evidence = {chunk.document_id for chunk in response.retrieved_evidence}
    assert old.document_id in evidence and new.document_id not in evidence


def test_a_withdrawal_with_no_known_replacement_is_said_plainly(corpus) -> None:
    from datetime import UTC, datetime

    settings, service, old, kfs, new = corpus
    with at(date(2025, 6, 2)):
        service.set_lifecycle(kfs.document_id, DocumentLifecycle.WITHDRAWN, "https://www.rbi.org.in/x",
                              "RBI marks this document with its official Withdrawn watermark.",
                              datetime(2025, 6, 2, 9, tzinfo=UTC), "AUTOMATED")
        response = RegulatoryQueryService(settings).query("What must the Key Facts Statement given to borrowers contain for a loan?")

    (notice,) = [item for item in response.notices if item.kind == "withdrawn"]
    assert notice.text == (
        "Key Facts Statement is withdrawn (detected 2 June 2025); no replacement was found in the indexed RBI corpus."
    )
    assert kfs.document_id not in {chunk.document_id for chunk in response.retrieved_evidence}


def test_no_notice_when_nothing_changed(corpus) -> None:
    settings, service, old, kfs, new = corpus

    response = ask(settings, date(2025, 6, 2))

    assert response.notices == []
    assert not response.answer.startswith("### What changed")


def test_an_answer_carries_at_most_one_withdrawal_notice(corpus) -> None:
    from datetime import UTC, datetime

    settings, service, old, kfs, new = corpus
    with at(date(2025, 6, 2)):
        for document in (old, kfs):  # two withdrawn rules, neither with a known replacement
            service.set_lifecycle(document.document_id, DocumentLifecycle.WITHDRAWN, "https://www.rbi.org.in/x",
                                  "Withdrawn watermark", datetime(2025, 6, 2, 9, tzinfo=UTC), "AUTOMATED")
        response = RegulatoryQueryService(settings).query("What must lenders disclose to borrowers for digital loans?")

    assert [item.kind for item in response.notices].count("withdrawn") == 1
