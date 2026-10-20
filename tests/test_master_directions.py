"""Index rows below are real rows from RBI's Master Directions index (October 2026)."""

from datetime import date
from pathlib import Path

from app.monitoring.master_directions import decide_inclusion, parse_index

ROWS = """<table>
<tr><td><a class="link2" href=BS_ViewMasDirections.aspx?id=12957> Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions, 2025 (updated as on July 15, 2026)</a></td><td  nowrap colspan=3><a id='APDF_347MD5CC21D3597C04354B67A42A1A4CB439C' target='_blank' href='https://rbidocs.rbi.org.in/rdocs/notification/PDFs/347MD5CC21D3597C04354B67A42A1A4CB439C.PDF' aria-labelledby='x'><img alt='PDF' src='../Images/pdf.gif'></a> <span id='SPDF_347' aria-hidden="true">542 kb</span></td></tr>
<tr><td><a class="link2" href=BS_ViewMasDirections.aspx?id=12931> Reserve Bank of India (Non-Banking Financial Companies – Miscellaneous) Directions, 2025 (Updated as on February 26, 2026)</a></td><td  nowrap colspan=3><a id='APDF_373' target='_blank' href='https://rbidocs.rbi.org.in/rdocs/notification/PDFs/373MD7F3656C99F764E2F9CE1BC4A1337861F.PDF'><img alt='PDF'></a> <span aria-hidden="true">330 kb</span></td></tr>
<tr><td><a class="link2" href=BS_ViewMasDirections.aspx?id=13149> Reserve Bank of India (Commercial Banks – Interest Rates on Advances) Directions, 2025</a></td><td  nowrap colspan=3><a target='_blank' href='https://rbidocs.rbi.org.in/rdocs/notification/PDFs/X1.PDF'><img alt='PDF'></a> <span aria-hidden="true">300 kb</span></td></tr>
</table>"""
RULE = Path(__file__).resolve().parents[1] / "config" / "corpus" / "inclusion.yaml"


def test_index_rows_give_page_pdf_size_and_update_date() -> None:
    first, second, third = parse_index(ROWS)

    assert first.page_id == "12957"
    assert first.page_url == "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12957"
    assert first.title.startswith("Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities)")
    assert first.pdf_file_name == "347MD5CC21D3597C04354B67A42A1A4CB439C.PDF"
    assert first.size_kb == 542
    assert first.updated_as_on == date(2026, 7, 15)  # lower-case "updated" on RBI's page
    assert second.updated_as_on == date(2026, 2, 26)
    assert third.updated_as_on is None


def test_inclusion_follows_the_written_rule_with_a_reason_for_each_entry() -> None:
    decisions = {item.entry.page_id: item for item in decide_inclusion(parse_index(ROWS), RULE)}

    assert decisions["12957"].included and "Credit Facilities" in decisions["12957"].reason
    assert not decisions["12931"].included and "no lending topic" in decisions["12931"].reason
    assert not decisions["13149"].included and "outside the corpus scope" in decisions["13149"].reason
