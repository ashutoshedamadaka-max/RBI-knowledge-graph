"""Successor evidence. The repeal annex fixture is real RBI text; sentence cases are synthetic."""

from datetime import date, datetime, UTC
from pathlib import Path

from app.corpus.identifiers import find_references
from app.models.documents import DocumentMetadata
from app.models.links import LinkRelation, LinkScope
from app.monitoring.successors import find_backward_links, find_forward_links, match_documents

FIXTURES = Path(__file__).parent / "fixtures" / "rbi_headers"
OWN = frozenset({"RBI/2025-26/36", "DOR.STR.REC.19/21.07.001/2025-26"})


def _digital_lending() -> str:
    return (FIXTURES / "digital_lending_repeal_section.txt").read_text(encoding="utf-8")


def test_the_repeal_annex_gives_exactly_the_three_listed_circulars() -> None:
    links = find_forward_links(_digital_lending(), OWN)

    assert [link.target_references for link in links] == [
        ["RBI/2019-20/258", "DOR(NBFC)(PD)CC.112/03.10.001/2019-20"],
        ["RBI/2022-23/111", "DOR.CRE.REC.66/21.07.001/2022-23"],
        ["RBI/2023-24/41", "DOR.CRE.REC.21/21.07.001/2023-24"],
    ]
    assert [link.target_date for link in links] == [date(2020, 6, 24), date(2022, 9, 2), date(2023, 6, 8)]
    assert all(link.relation is LinkRelation.SUPERSEDES and link.scope is LinkScope.WHOLE for link in links)
    assert links[1].target_title == "Guidelines on Digital Lending"


def test_circulars_cited_in_footnotes_or_as_amended_are_not_repealed() -> None:
    text = _digital_lending()
    keys = {key for link in find_forward_links(text, OWN) for key in link.target_references}

    # The fixture cites the KFS and penal-charges circulars "as amended from time to time"
    # and, in a footnote, a recovery-agent circular. Only the annex rows are repealed.
    assert "DOR.STR.REC.13/13.03.00/2024-25" in {r.key for r in find_references(text)}  # the citation is really there
    assert keys == {
        "RBI/2019-20/258", "DOR(NBFC)(PD)CC.112/03.10.001/2019-20",
        "RBI/2022-23/111", "DOR.CRE.REC.66/21.07.001/2022-23",
        "RBI/2023-24/41", "DOR.CRE.REC.21/21.07.001/2023-24",
    }


def test_every_quote_is_an_exact_piece_of_the_source_and_shows_its_target() -> None:
    text = _digital_lending()

    for link in find_forward_links(text, OWN):
        assert link.evidence_quote in text
        assert link.target_references[0].startswith("RBI/")
        assert link.target_references[0] in link.evidence_quote.replace(" ", "")


def test_the_annex_ends_where_the_table_ends() -> None:
    text = (
        "Annex III: List of circulars to be repealed with the issuance of these Directions\n"
        "S.No. \nCircular No. \nDate \nSubject \n"
        "1. \nRBI/2019-20/258\n DOR(NBFC)(PD) CC.No.112/03.10.001/2019-20 \n24.06.2020 \nLoans Sourced by Banks \n"
        "1 Circular DOR.ORG.REC.65/21.04.158/2022-23 on 'Outsourcing' dated August 12, 2022.\n"
    )

    links = find_forward_links(text)

    assert len(links) == 1


def test_an_index_entry_for_the_annex_is_not_a_table() -> None:
    text = "Annex III: List of circulars to be repealed with the issuance of these Directions\nChapter VII: General\n"

    assert find_forward_links(text) == []


def test_a_sentence_repealing_a_whole_circular_is_found_with_its_date() -> None:
    text = "7. The Master Direction DOR.MRG.77/00-00-007/2022-23 dated October 11, 2022 stands repealed with immediate effect.\n"

    (link,) = find_forward_links(text)

    assert link.target_references == ["DOR.MRG.77/00-00-007/2022-23"]
    assert link.target_date == date(2022, 10, 11)
    assert link.scope is LinkScope.WHOLE and link.method == "repeal_sentence"


def test_a_supersession_sentence_lists_each_document_it_names() -> None:
    text = (
        "These Directions supersede the following circulars:\n"
        "i. DOR.CRE.REC.66/21.07.001/2022-23 dated September 2, 2022\n"
        "ii. DOR.CRE.REC.21/21.07.001/2023-24 dated June 8, 2023\n"
    )

    links = find_forward_links(text)

    assert [item.target_references for item in links] == [["DOR.CRE.REC.66/21.07.001/2022-23"], ["DOR.CRE.REC.21/21.07.001/2023-24"]]
    assert all(item.method == "supersession_sentence" for item in links)


def test_a_partial_repeal_is_marked_partial() -> None:
    text = "Paragraph 5 of the circular DOR.CRE.REC.66/21.07.001/2022-23 dated September 2, 2022 stands repealed.\n"

    (link,) = find_forward_links(text)

    assert link.scope is LinkScope.PARTIAL


def test_a_document_never_repeals_its_own_number() -> None:
    text = "RBI/2025-26/36 DOR.STR.REC.19/21.07.001/2025-26 supersedes earlier instructions on digital lending.\n"

    assert find_forward_links(text, OWN) == []


def test_a_self_withdrawal_without_a_named_replacement_is_not_a_link() -> None:
    assert find_forward_links("This circular stands withdrawn.\n") == []
    assert find_backward_links("This circular stands withdrawn.") == []


def test_an_old_page_that_names_its_replacement_is_a_backward_link() -> None:
    text = "This circular has been superseded by circular DOR.STR.REC.19/21.07.001/2025-26 dated May 8, 2025.\nFurther text."

    (link,) = find_backward_links(text)

    assert link.target_references == ["DOR.STR.REC.19/21.07.001/2025-26"]
    assert link.target_date == date(2025, 5, 8)
    assert link.evidence_in == "old" and link.scope is LinkScope.WHOLE
    assert link.evidence_quote in text


def test_an_amendment_names_the_document_it_changes_by_title() -> None:
    text = (
        "Lending to Micro, Small & Medium Enterprises (MSME) Sector (Amendment) Directions, 2026\n"
        "Please refer to the Master Direction - Lending to Micro, Small & Medium Enterprises (MSME) Sector "
        "(Updated as on July 23, 2025) (hereinafter referred to as “the Directions”).\n"
        "3. The Amendment Directions modify the Directions as below:\n"
    )

    (link,) = find_forward_links(text)

    assert link.relation is LinkRelation.AMENDS and link.scope is LinkScope.PARTIAL
    assert link.target_title == "Master Direction - Lending to Micro, Small & Medium Enterprises (MSME) Sector"


def test_a_master_circular_reissue_is_only_a_candidate() -> None:
    text = (
        "Master Circular - Management of Advances - UCBs\n"
        "Please refer to the Master Circular DOR.CRE.REC.No.27/07.10.002/2023-24 dated July 25, 2023.\n"
        "2. Attached is the revised Master Circular.\n"
    )

    (link,) = find_forward_links(text)

    assert link.relation is LinkRelation.CANDIDATE
    assert link.target_references == ["DOR.CRE.REC.27/07.10.002/2023-24"]


def _document(document_id, title, numbers, issued=None, department="DOR") -> DocumentMetadata:
    return DocumentMetadata(
        document_id=document_id, title=title, content_hash=document_id, file_name="p.html", mime_type="text/html",
        ingested_at=datetime.now(UTC), circular_numbers=numbers, publication_date=issued, issuing_department=department,
    )


def test_a_link_is_matched_to_corpus_documents_by_either_printed_number() -> None:
    old = _document("old", "Guidelines on Digital Lending", ["RBI/2022-23/111", "DOR.CRE.REC.66/21.07.001/2022-23"])
    other = _document("other", "Something else", ["RBI/2024-25/1"])
    (link,) = [item for item in find_forward_links(_digital_lending(), OWN) if item.target_references[0] == "RBI/2022-23/111"]

    assert match_documents(link, [other, old]) == [old]


def test_a_title_target_needs_an_exact_title_match() -> None:
    base = _document("base", "Master Direction - Lending to Micro, Small & Medium Enterprises (MSME) Sector", [])
    near = _document("near", "Master Direction - Lending to MSME Sector", [])
    text = ("Amendment Directions modify.\nPlease refer to the Master Direction - Lending to Micro, Small & Medium "
            "Enterprises (MSME) Sector (Updated as on July 23, 2025) (hereinafter referred to as “the Directions”).\n")
    (link,) = find_forward_links(text)

    assert match_documents(link, [near, base]) == [base]


def test_a_citation_in_the_next_list_item_is_not_swept_into_a_repeal_sentence() -> None:
    text = (
        "i. The circular DOR.CRE.REC.66/21.07.001/2022-23 dated September 2, 2022 stands repealed.\n"
        "ii. Penal charges are governed by circular no. DoR.MCS.REC.28/01.01.001/2023-24 as amended from time to time.\n"
    )

    links = find_forward_links(text)

    assert [item.target_references for item in links] == [["DOR.CRE.REC.66/21.07.001/2022-23"]]


def test_a_repeal_sentence_wrapped_over_two_lines_is_still_read_whole() -> None:
    text = (
        "The instructions in circular DOR.CRE.REC.66/21.07.001/2022-23 dated September 2, 2022\n"
        "stand repealed with effect from the date of these Directions.\n"
        "3. Applicability: circular DOR.STR.REC.13/13.03.00/2024-25 continues to apply.\n"
    )

    links = find_forward_links(text)

    assert [item.target_references for item in links] == [["DOR.CRE.REC.66/21.07.001/2022-23"]]


def test_the_circular_that_announced_a_repeal_is_not_its_target() -> None:
    # Real wording from the NBFC Responsible Business Conduct Directions, 2025 (paragraph 106).
    text = (
        "106.With the issue of these Directions, the existing Directions, instructions, and \n"
        "guidelines relating to Responsible Business Conduct as applicable to Non-\n"
        "Banking Financial Companies stand repealed, as communicated vide circular \n"
        "DOR.RRC.REC.302/33-01-010/2025-26 dated November 28, 2025. The \n"
        "Directions, instructions, and guidelines repealed prior to the issuance of these \n"
        "Directions shall continue to remain repealed.\n"
    )

    assert find_forward_links(text) == []


def test_rbi_repeal_banner_on_an_old_page_is_a_backward_link() -> None:
    # Real banner on https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382 (Guidelines on Digital Lending).
    text = ("Guidelines on Digital Lending\n"
            "The Circular has been repealed. Please refer to Reserve Bank of India (Digital Lending) Directions, 2025 "
            "dated May 8, 2025.\nRBI/2022-23/111\n DOR.CRE.REC.66/21.07.001/2022-23\nSeptember 02, 2022\n")

    (link,) = find_backward_links(text)

    assert link.evidence_in == "old" and link.method == "superseded_by_statement"
    assert link.target_title == "Reserve Bank of India (Digital Lending) Directions, 2025"
    assert link.target_date == date(2025, 5, 8)
    assert link.evidence_quote in text and link.evidence_quote.startswith("The Circular has been repealed")
