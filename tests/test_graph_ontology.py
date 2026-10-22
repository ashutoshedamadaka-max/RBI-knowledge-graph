"""Phase 4 graph: one tested query per edge type, quotes that are real substrings, and labels scoring."""

from datetime import UTC, date, datetime

from app.evaluation.graph_metrics import score, sentence_of, sentences
from app.graph import ontology
from app.graph.llm_extraction import load_entities, resolve, validate
from app.models.documents import DocumentLifecycle, DocumentMetadata
from app.models.links import DocumentLink, LinkRelation, LinkScope, LinkTrust
from app.monitoring.withdrawn_register import RegisterEntry

NEW = ("Chapter I – Preliminary\n"
       "1. These Directions shall apply to every NBFC. “Digital lending” means a remote and automated lending process.\n"
       "2. An NBFC shall disclose the annual percentage rate to the borrower, as required in paragraph 1.\n"
       "3. The circular DOR.CRE.REC.66/21.07.001/2022-23 dated September 2, 2022 is repealed.\n")
OLD = "1. Regulated entities shall report digital lending apps to the Reserve Bank.\n"
AMENDMENT = "1. Paragraph 2 shall be deleted.\n"


def _document(document_id: str, title: str, lifecycle=DocumentLifecycle.ACTIVE, numbers=()) -> DocumentMetadata:
    return DocumentMetadata(document_id=document_id, title=title, content_hash=document_id, file_name="x.pdf",
                            mime_type="application/pdf", ingested_at=datetime.now(UTC), lifecycle=lifecycle,
                            circular_numbers=list(numbers), issuing_department="Department of Regulation",
                            source_url=f"https://www.rbi.org.in/{document_id}")


def _graph():
    documents = [_document("new", "Digital Lending Directions, 2025"),
                 _document("old", "Guidelines on Digital Lending", DocumentLifecycle.WITHDRAWN,
                           ["DOR.CRE.REC.66/21.07.001/2022-23"]),
                 _document("amend", "Digital Lending (Amendment) Directions, 2026")]
    pages = {"new": [NEW], "old": [OLD], "amend": [AMENDMENT]}
    links = [DocumentLink(link_id="l1", relation=LinkRelation.SUPERSEDES, scope=LinkScope.WHOLE, old_document_id="old",
                          new_document_id="new", method="repeal_annex", evidence_quote="is repealed",
                          trust=LinkTrust.APPROVED, created_at=datetime.now(UTC)),
             DocumentLink(link_id="l2", relation=LinkRelation.AMENDS, scope=LinkScope.PARTIAL, old_document_id="new",
                          new_document_id="amend", method="amendment", evidence_quote="shall be deleted",
                          created_at=datetime.now(UTC)),
             DocumentLink(link_id="l3", relation=LinkRelation.CANDIDATE, scope=LinkScope.WHOLE, old_document_id="old",
                          new_document_id="amend", method="content", evidence_quote="x", created_at=datetime.now(UTC))]
    entry = RegisterEntry("Circulars Withdrawn", "1", "Guidelines on Digital Lending", date(2022, 9, 2), None, ())
    graph, report = ontology.build_graph(documents, pages, links, {"old": entry}, "https://www.rbi.org.in/register")
    extraction = {"model": "test", "provisions": {"new#2": {"edges": [
        {"type": "APPLIES_TO", "entity": "nbfc", "quote": "An NBFC shall disclose", "confidence": 0.9},
        {"type": "REQUIRES", "entity": "nbfc", "quote": "An NBFC shall disclose the annual percentage rate",
         "confidence": 0.9, "obligation": "Disclose the APR"}]}}}
    report["llm"] = ontology.add_llm_edges(graph, extraction)
    return graph, report


def test_every_edge_type_has_a_working_query() -> None:
    graph, report = _graph()
    q = ontology.neighbours

    assert q(graph, "old", "SUPERSEDES", reverse=True) == ["new"]          # what replaced this?
    assert q(graph, "amend", "AMENDS") == ["new"]                          # what does this amend?
    assert q(graph, "old", "WITHDRAWS", reverse=True) == ["register:rbi-withdrawn"]
    assert q(graph, "new", "PART_OF", reverse=True) == ["new#1", "new#2", "new#3"]
    assert q(graph, "new#2", "REFERS_TO") == ["new#1"]                     # "as required in paragraph 1"
    assert q(graph, "new#3", "REFERS_TO") == ["old"]                       # a circular number in the corpus
    assert q(graph, "new#1", "DEFINES") == ["term:digital lending"]
    assert q(graph, "new#2", "APPLIES_TO") == ["entity:nbfc"]
    assert graph.nodes[q(graph, "new#2", "REQUIRES")[0]]["title"] == "Disclose the APR"
    assert q(graph, "new", "ISSUED_BY") == ["authority:Department of Regulation"]
    assert set(report["edges"]) | {"APPLIES_TO", "REQUIRES"} >= set(ontology.EDGE_TYPES)


def test_quotes_are_real_text_and_guesses_are_not_edges() -> None:
    graph, report = _graph()

    for source, _, data in graph.edges(data=True):
        if data["quote"] and data["method"] in {"pattern", "llm"}:
            assert data["quote"] in graph.nodes[source]["text"]
    assert not graph.has_edge("amend", "old")  # the CANDIDATE link is a suggestion, not an edge
    # An amendment's "Paragraph 2" is the amended document's paragraph: counted, never linked to itself.
    assert report["failures"]["paragraph_reference_in_amendment"] == 1
    assert ontology.neighbours(graph, "amend#1", "REFERS_TO") == []


def test_llm_edges_need_a_real_quote_and_a_listed_entity() -> None:
    entities = load_entities()
    text = "An NBFC-ML shall put in place a Board approved policy on loans."
    raw = {"applies_to": [{"entity": "middle layer NBFC", "quote": "An NBFC-ML shall put in place", "confidence": 1},
                          {"entity": "nbfc-ml", "quote": "An NBFC-ML shall put", "confidence": 1},
                          {"entity": "space agency", "quote": "Board approved policy", "confidence": 1}],
           "requires": [{"bearer": "nbfc-ml", "obligation": "Adopt a policy", "quote": "a policy it invented", "confidence": 1}]}

    edges, dropped = validate(raw, text, entities)

    assert [(edge["type"], edge["entity"]) for edge in edges] == [("APPLIES_TO", "nbfc-ml")]  # alias resolved
    assert dropped == {"APPLIES_TO:duplicate": 1, "APPLIES_TO:entity_not_on_list": 1, "REQUIRES:quote_not_in_provision": 1}
    assert resolve("NBFCs", entities) == "nbfc" and resolve("Core Investment Company", entities) == "cic"


def test_extracted_quotes_are_scored_by_the_sentence_they_fall_in() -> None:
    parts = sentences("1. An NBFC shall disclose the APR. It shall also publish its policy.\n(i) on its website;")

    assert parts == ["1. An NBFC shall disclose the APR.", "It shall also publish its policy.", "(i) on its website;"]
    assert sentence_of("It shall also publish its policy", parts) == {2}
    result = score({"p": {1, 2}}, {"p": {2, 3}})
    assert result["precision"]["numerator"] == 1 and result["recall"]["denominator"] == 2
