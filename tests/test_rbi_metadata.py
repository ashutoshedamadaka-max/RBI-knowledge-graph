"""Header facts from real RBI pages. Expected values are copied from the printed headers."""

from datetime import date
from pathlib import Path

import pytest

from app.corpus.identifiers import find_references, normalise_department_reference, parse_date
from app.monitoring.metadata import extract_rbi_document_facts

FIXTURES = Path(__file__).parent / "fixtures" / "rbi_headers"

CASES = [
    ("digital_lending_directions_2025", ["RBI/2025-26/36", "DOR.STR.REC.19/21.07.001/2025-26"],
     # "These Directions shall come into force immediately except for para 6 ..." -> in force on issue.
     date(2025, 5, 8), None, "DOR", "directions", "Reserve Bank of India (Digital Lending) Directions, 2025"),
    ("penal_charges_2023", ["RBI/2023-24/53", "DOR.MCS.REC.28/01.01.001/2023-24"],
     date(2023, 8, 18), date(2024, 1, 1), "DOR", "circular", "Fair Lending Practice - Penal Charges in Loan Accounts"),
    ("property_documents_release", ["RBI/2023-24/60", "DOR.MCS.REC.38/01.01.001/2023-24"],
     date(2023, 9, 13), None, "DOR", "circular", None),
    ("floating_rate_reset_master_direction_page", ["RBI/2023-24/55", "DOR.MCS.REC.32/01.01.003/2023-24"],
     date(2023, 8, 18), None, "DOR", "circular", None),
    ("irac_master_circular_2025", ["RBI/2025-26/13", "DOR.STR.REC.9/21.04.048/2025-26"],
     date(2025, 4, 1), None, "DOR", "master_circular", None),
    ("ucb_management_of_advances_master_circular", ["RBI/2025-26/18", "DOR.CRE.REC.13/07.10.002/2025-26"],
     date(2025, 4, 1), None, "DOR", "master_circular", "Master Circular - Management of Advances - UCBs"),
    ("psl_amendment_2026", ["RBI/FIDD/2025-26/196", "FIDD.CO.PSD.BC.11/04.09.001/2025-26"],
     date(2026, 1, 19), None, "FIDD", "amendment", None),
    ("psl_second_amendment_2026", ["RBI/2026-27/232", "FIDD.CO.PSD.BC.08/04.09.001/2026-27"],
     date(2026, 8, 7), None, "FIDD", "amendment", None),
    ("psl_third_amendment_2026", ["RBI/2026-27/256", "FIDD.CO.PSD.BC.10/04.09.001/2026-27"],
     date(2026, 9, 11), None, "FIDD", "amendment", None),
    ("msme_amendment_2026", ["RBI/2025-26/206", "FIDD.MSME&NFS.BC.12/06.02.31/2025-26"],
     date(2026, 2, 9), None, "FIDD", "amendment", None),
    ("fema_borrowing_lending_ap_dir_22", ["RBI/2025-26/221", "A.P. (DIR SERIES) CIRCULAR NO. 22"],
     date(2026, 2, 16), None, "FED", "amendment", None),
    ("fema_notification_3r5", ["FEMA 3(R)(5)/2026-RB"],
     date(2026, 2, 9), None, "FED", "amendment", None),
    ("psl_faqs_page", [], None, None, None, "faq", "FAQs on Priority Sector Lending (PSL)"),
]


@pytest.mark.parametrize("name, numbers, issued, effective, department, kind, title", CASES)
def test_header_facts_match_the_printed_rbi_header(name, numbers, issued, effective, department, kind, title) -> None:
    facts = extract_rbi_document_facts((FIXTURES / f"{name}.txt").read_text(encoding="utf-8"))

    assert facts.reference_numbers == numbers
    assert facts.issue_date == issued
    assert facts.effective_date == effective
    assert facts.issuing_department == department
    assert facts.document_type == kind
    if title:
        assert facts.title == title


def test_an_update_date_is_not_taken_as_the_issue_date() -> None:
    facts = extract_rbi_document_facts((FIXTURES / "psl_faqs_page.txt").read_text(encoding="utf-8"))

    assert facts.issue_date is None  # the page prints only "(Updated as on September 11, 2026)"


@pytest.mark.parametrize("cited, key", [
    ("DOR.CRE.REC .66/21.07.001/2022-23", "DOR.CRE.REC.66/21.07.001/2022-23"),
    ("DOR.CRE.REC.No.13/07.10.002/2025-26", "DOR.CRE.REC.13/07.10.002/2025-26"),
    ("DOR(NBFC)(PD) CC.No.112/03.10.001/2019-20", "DOR(NBFC)(PD)CC.112/03.10.001/2019-20"),
    ("RPCD No.Plan.BC92/04.09.01/2003-04", "RPCD.PLAN.BC92/04.09.01/2003-04"),
    ("CEPD. PRD. No.S873/13.01.001/2021-22", "CEPD.PRD.S873/13.01.001/2021-22"),
])
def test_differently_printed_references_share_one_key(cited, key) -> None:
    assert normalise_department_reference(cited) == key


@pytest.mark.parametrize("sentence, key", [
    ("Please refer to our circular no. DBR.No.Dir.BC.10/13.03.00/2015-16 dated July 01, 2015", "DBR.DIR.BC.10/13.03.00/2015-16"),
    ("RBI circular FMOD.MAOG.No.S-56/01.06.016/2026-27 dated June 08, 2026", "FMOD.MAOG.S-56/01.06.016/2026-27"),
    ("our Master Direction DOR.MRG.77/00-00-007/2022-23 dated October 11, 2022", "DOR.MRG.77/00-00-007/2022-23"),
    ("issued vide circular DBR.Leg.No.BC.15/09.08.020/2018-19", "DBR.LEG.BC.15/09.08.020/2018-19"),
])
def test_a_citing_sentence_does_not_become_part_of_the_reference(sentence, key) -> None:
    assert [item.key for item in find_references(sentence)] == [key]


def test_reference_scan_stays_fast_on_long_text_without_references() -> None:
    import time

    text = ("Circular No. dated the regulated entities shall ensure. " * 4000) + "DOR.STR.REC.19/21.07.001/2025-26"
    started = time.perf_counter()
    found = find_references(text)
    assert [item.key for item in found] == ["DOR.STR.REC.19/21.07.001/2025-26"]
    assert time.perf_counter() - started < 1.0


def test_dates_in_rbi_formats() -> None:
    assert parse_date("May 8, 2025") == date(2025, 5, 8)
    assert parse_date("February 09, 2026") == date(2026, 2, 9)
    assert parse_date("24.06.2020") == date(2020, 6, 24)  # repeal annex tables are day first
    assert parse_date("31.02.2020") is None


def test_the_effective_date_comes_only_from_the_document_commencement_clause() -> None:
    def effective(sentence: str):
        return extract_rbi_document_facts(f"RBI/2025-26/1\nMay 1, 2025\n{sentence}").effective_date

    assert effective("These Directions shall come into effect from November 1, 2025.") == date(2025, 11, 1)
    assert effective("These instructions shall come into effect from January 1, 2024.") == date(2024, 1, 1)
    # Paragraph dates and provision dates are not the document's date (real RBI wording).
    assert effective("These Directions shall come into force immediately except for para 6, which shall come "
                     "into effect from November 1, 2025.") is None
    assert effective("These Directions shall come into effect on the day it is placed on the official website of "
                     "the Reserve Bank. Provided that, the Directions under Part B shall come into force from "
                     "January 1, 2026.") is None
    assert effective("This provision is effective from November 15, 2024.") is None
    assert effective("In case of existing loans, the switchover shall be applicable from June 30, 2024.") is None
