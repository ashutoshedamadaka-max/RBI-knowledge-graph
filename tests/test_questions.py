from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.evaluation.questions import Paragraph, plan, to_item, word_overlap
from app.evaluation.retrieval_metrics import boundary_kept, first_hit_rank, summarise
from app.models.documents import DocumentLifecycle, DocumentMetadata

TEXT = ("9. A Key Facts Statement shall be provided to every prospective borrower before the loan contract is "
        "executed. It shall be in a language understood by the borrower.")


def paragraph(label="9", text=TEXT, url="https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12942",
              issued=date(2025, 11, 28), lifecycle=DocumentLifecycle.REVIEW_REQUIRED) -> Paragraph:
    document = DocumentMetadata(document_id=f"doc_{label}_{issued}", title="NBFC Responsible Business Conduct",
                                content_hash="x", file_name="x", mime_type="x", ingested_at=datetime.now(UTC),
                                source_url=url, publication_date=issued, lifecycle=lifecycle)
    return Paragraph(document, label, text)


def draft(span: str, question: str = "Before signing, what must an NBFC hand a would-be borrower?") -> dict:
    return {"question": question, "evidence_span": span, "second_evidence_span": "",
            "reference_answer": "A Key Facts Statement.", "altered_fact": ""}


def planned(kind="single_fact", source=None) -> dict:
    return {"type": kind, "split": "dev", "sources": [source or paragraph()], "as_of": None}


def test_a_draft_must_quote_its_source_exactly_and_meaningfully() -> None:
    good = to_item(1, planned(), draft("A Key Facts Statement shall be provided to every prospective borrower"), "m")
    assert good["gold"][0]["span"].startswith("A Key Facts Statement") and good["gold"][0]["paragraph"] == "9"
    assert to_item(2, planned(), draft("A KFS shall be given to each borrower"), "m") is None  # paraphrase, not a quote
    assert to_item(3, planned(), draft("9."), "m") is None  # too short to be a sentence


def test_a_trap_question_keeps_the_withdrawn_sentence_as_must_not_cite() -> None:
    item = to_item(4, planned("withdrawn_trap"), draft("A Key Facts Statement shall be provided to every prospective borrower"), "m")

    assert item["gold"] == [] and item["must_not_cite"][0]["paragraph"] == "9"
    assert "never cite" in item["expected"]


def test_word_overlap_measures_copying() -> None:
    span = "A Key Facts Statement shall be provided to every prospective borrower"
    assert word_overlap("Must a Key Facts Statement be provided to every prospective borrower?", span) > 0.8
    assert word_overlap("Before signing, what must an NBFC hand a would-be borrower?", span) < 0.3


def test_the_plan_is_reproducible_and_splits_about_a_third_to_test() -> None:
    pool = {"current": [paragraph(str(n), f"{n}. Paragraph {n} applies to NBFCs and refers to paragraph {n + 1}. " * 3)
                        for n in range(1, 80)],
            "withdrawn": [paragraph(f"w{n}", TEXT, issued=date(2023, 1, 1), lifecycle=DocumentLifecycle.WITHDRAWN)
                          for n in range(1, 40)]}
    first, again = plan(pool, ["Interest Equalisation Scheme"]), plan(pool, ["Interest Equalisation Scheme"])

    assert [(item["type"], item["split"]) for item in first] == [(item["type"], item["split"]) for item in again]
    single = [item for item in first if item["type"] == "single_fact"]
    assert len(single) == 50 and sum(item["split"] == "test" for item in single) == round(50 / 3)
    change = [item for item in first if item["type"] == "change_over_time"]
    assert change and all(date(2023, 1, 1) < date.fromisoformat(item["as_of"]) < date(2025, 11, 28) for item in change)


def test_a_gold_hit_needs_the_same_rbi_page_and_the_whole_sentence() -> None:
    gold = {"url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12942",
            "span": "A Key Facts Statement shall be provided to every prospective borrower"}
    def chunk(url, text):
        return SimpleNamespace(source_url=url, text=text)
    results = [chunk("https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=1", TEXT),       # right text, wrong page
               chunk("https://rbi.org.in/scripts/bs_viewmasdirections.aspx?id=12942", "9. A Key Facts\nStatement"),  # cut
               chunk("https://rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=12942", TEXT.replace(" ", "\n"))]

    assert first_hit_rank(results, gold) == 3
    assert boundary_kept(results, gold) and not boundary_kept(results[:2], gold)
    assert summarise([3, None, 1])["recall@5"]["numerator"] == 2 and summarise([3, None, 1])["mrr"] == round((1 / 3 + 1) / 3, 4)
