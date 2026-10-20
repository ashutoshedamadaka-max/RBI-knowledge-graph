from datetime import UTC, date, datetime

import pytest

from app.models.documents import DocumentLifecycle, DocumentMetadata
from app.models.links import LinkRelation, LinkScope, LinkTrust
from app.monitoring.trust import decide_trust, is_rbi_owned


def doc(document_id, issued, url="https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=1", lifecycle=DocumentLifecycle.REVIEW_REQUIRED):
    return DocumentMetadata(document_id=document_id, title=document_id, content_hash=document_id, file_name="p.html",
                            mime_type="text/html", ingested_at=datetime.now(UTC), publication_date=issued,
                            source_url=url, lifecycle=lifecycle)


def decide(**overrides):
    values = dict(relation=LinkRelation.SUPERSEDES, scope=LinkScope.WHOLE, method="repeal_annex",
                  evidence_quote="RBI/2022-23/111 ... 02.09.2022 Guidelines on Digital Lending",
                  new=doc("new", date(2025, 5, 8)), old=doc("old", date(2022, 9, 2)),
                  matched_old_count=1, auto_trust_enabled=True)
    return decide_trust(**{**values, **overrides})


def test_explicit_whole_repeal_on_rbi_domain_with_later_date_is_auto_trusted() -> None:
    decision = decide()

    assert decision.trust is LinkTrust.AUTO_TRUSTED
    assert decision.reasons


@pytest.mark.parametrize("method", ["repeal_sentence", "supersession_sentence", "superseded_by_statement"])
def test_every_explicit_statement_type_can_be_trusted(method) -> None:
    assert decide(method=method).trust is LinkTrust.AUTO_TRUSTED


@pytest.mark.parametrize("name, overrides, reason", [
    ("switched off", dict(auto_trust_enabled=False), "switched off"),
    ("amendment", dict(relation=LinkRelation.AMENDS), "amends"),
    ("candidate", dict(relation=LinkRelation.CANDIDATE), "candidate"),
    ("partial repeal", dict(scope=LinkScope.PARTIAL), "part of the old"),
    ("master circular reissue", dict(method="master_circular_reissue"), "not an explicit"),
    ("similar title only", dict(method="candidate_title_similarity"), "not an explicit"),
    ("no quote", dict(evidence_quote="  "), "no quoted evidence"),
    ("ambiguous match", dict(matched_old_count=2), "2 documents"),
    ("no match", dict(matched_old_count=0), "0 documents"),
    ("new not on RBI domain", dict(new=doc("new", date(2025, 5, 8), url="https://example.com/rbi")), "RBI-owned"),
    ("old not on RBI domain", dict(old=doc("old", date(2022, 9, 2), url="https://rbi.org.in.evil.com/x")), "RBI-owned"),
    ("new issue date missing", dict(new=doc("new", None)), "date is missing"),
    ("old issue date missing", dict(old=doc("old", None)), "date is missing"),
    ("new issued earlier", dict(new=doc("new", date(2021, 1, 1))), "not issued after"),
    ("new issued the same day", dict(new=doc("new", date(2022, 9, 2))), "not issued after"),
    ("new is withdrawn", dict(new=doc("new", date(2025, 5, 8), lifecycle=DocumentLifecycle.WITHDRAWN)), "withdrawn"),
    ("replaces itself", dict(new=doc("same", date(2025, 5, 8)), old=doc("same", date(2022, 9, 2))), "itself"),
])
def test_any_failed_condition_sends_the_link_to_review(name, overrides, reason) -> None:
    decision = decide(**overrides)

    assert decision.trust is LinkTrust.REVIEW_REQUIRED, name
    assert any(reason in item for item in decision.reasons), decision.reasons


def test_all_failed_conditions_are_listed_not_just_the_first() -> None:
    decision = decide(scope=LinkScope.PARTIAL, matched_old_count=2, new=doc("new", date(2021, 1, 1)))

    assert len(decision.reasons) == 3


def test_rbi_domain_check_is_exact_not_a_substring() -> None:
    assert is_rbi_owned("https://www.rbi.org.in/Scripts/x") and is_rbi_owned("https://rbi.org.in/x")
    assert not is_rbi_owned("https://notrbi.org.in/x")
    assert not is_rbi_owned("https://rbi.org.in.evil.com/x")
    assert not is_rbi_owned(None)
