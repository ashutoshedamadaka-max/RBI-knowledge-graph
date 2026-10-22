"""The Phase 4 knowledge graph: seven node types, nine edge types, every edge with its evidence.

Built from a corpus in one pass, cheapest and most reliable extraction first:
structure (PART_OF, from the chunker's paragraph segmentation), document links (SUPERSEDES / AMENDS
from the link store), RBI's withdrawn register (WITHDRAWS), patterns (REFERS_TO, DEFINES) and the
issuing department (ISSUED_BY). APPLIES_TO and REQUIRES come from the quoted LLM extraction in
app/graph/llm_extraction.py. An edge that claims a quote carries one that is an exact substring
of its source text.
"""
import json
import re
from collections import Counter
from pathlib import Path

import networkx as nx

from app.corpus.identifiers import find_references
from app.ingestion.chunkers import segment
from app.models.links import LinkRelation, LinkTrust

NODE_TYPES = ("Document", "Provision", "RegulatedEntity", "Product", "Obligation", "DefinedTerm", "Authority")
EDGE_TYPES = ("AMENDS", "SUPERSEDES", "WITHDRAWS", "PART_OF", "APPLIES_TO", "REQUIRES", "REFERS_TO", "DEFINES",
              "ISSUED_BY")  # ISSUED_BY: decision D10, kept by Ashu (22 Oct 2026)

_NUMBERED = re.compile(r"\d{1,3}")
# "paragraph 5", "paragraphs 5 and 6", "para 12(b)"; "of the <other> Directions/Circular" makes it external.
_PARAGRAPH_REF = re.compile(r"\b(?:paragraphs?|paras?)\s+(\d{1,3})\b((?:\s*(?:,|and|to)\s*\d{1,3}\b)*)", re.IGNORECASE)
_EXTERNAL = re.compile(r"\s*(?:\([^)]{0,12}\)\s*)?(?:of|under|in)\s+(?:the\s+)?(?!these\b|this\b)[A-Z\"“]")
_AMENDING = re.compile(r"\bamendment\b", re.IGNORECASE)
_DEFINITION = re.compile(r"[“\"]([^”\"]{2,80})[”\"]\s*(?:,\s*)?(?:means|shall mean|includes|shall include|refers to)\b")


def provision_id(document_id: str, label: str, seen: Counter) -> str:
    """Stable within a document; a label RBI reuses (annexes restart numbering) gets ~2, ~3."""
    seen[label] += 1
    return f"{document_id}#{label}" + (f"~{seen[label]}" if seen[label] > 1 else "")


def _edge(graph: nx.MultiDiGraph, source: str, target: str, kind: str, method: str, quote: str | None = None,
          **extra) -> None:
    graph.add_edge(source, target, type=kind, method=method, quote=quote, **extra)


def build_graph(documents: list, pages: dict[str, list[str]], links: list, register: dict | None = None,
                register_url: str | None = None) -> tuple[nx.MultiDiGraph, dict]:
    """The graph and an extraction report (counts by type, and every failure to resolve)."""
    graph = nx.MultiDiGraph()
    failures: Counter = Counter()
    by_number = {}
    for document in documents:
        graph.add_node(document.document_id, type="Document", title=document.title, url=document.source_url,
                       lifecycle=document.lifecycle.value, issued=str(document.publication_date or ""),
                       in_force_from=str(document.in_force_from or ""), in_force_to=str(document.in_force_to or ""))
        for number in document.circular_numbers:
            by_number.setdefault(number, document.document_id)
        authority = document.issuing_department or "Reserve Bank of India"
        graph.add_node(f"authority:{authority}", type="Authority", title=authority)
        _edge(graph, document.document_id, f"authority:{authority}", "ISSUED_BY", "metadata")

    for document in documents:
        seen: Counter = Counter()
        provisions, texts = {}, {}
        for unit in segment(pages[document.document_id]):
            if not _NUMBERED.fullmatch(unit.label):
                continue  # preamble, headings-only text and contents pages are not provisions
            node = provision_id(document.document_id, unit.label, seen)
            text = "\n".join(unit.lines)
            provisions.setdefault(unit.label, node)  # the first paragraph with a number answers "paragraph N"
            texts[node] = text
            graph.add_node(node, type="Provision", document_id=document.document_id, label=unit.label,
                           heading=" > ".join(unit.heading_path), page=unit.page, text=text)
            _edge(graph, node, document.document_id, "PART_OF", "structure")
            for match in _DEFINITION.finditer(text):
                term = re.sub(r"\s+", " ", match.group(1)).strip()
                term_node = f"term:{term.lower()}"
                graph.add_node(term_node, type="DefinedTerm", title=term)
                _edge(graph, node, term_node, "DEFINES", "pattern", _sentence(text, match.start()))
        for node, text in texts.items():
            _references(graph, node, text, provisions, by_number, document.document_id, failures,
                        amending=bool(_AMENDING.search(document.title or "")))

    for link in links:
        if link.relation is LinkRelation.CANDIDATE or link.trust is LinkTrust.REJECTED:
            continue  # a content-matched guess is not an edge until a reviewer approves it as a real relation
        if link.old_document_id in graph and link.new_document_id in graph:
            _edge(graph, link.new_document_id, link.old_document_id, link.relation.value, link.method,
                  link.evidence_quote, trust=link.trust.value, scope=link.scope.value, evidence_url=link.evidence_url)

    if register:
        graph.add_node("register:rbi-withdrawn", type="Document", title="RBI register of withdrawn circulars",
                       url=register_url, lifecycle="ACTIVE", in_corpus=False)
        for document_id, entry in register.items():
            _edge(graph, "register:rbi-withdrawn", document_id, "WITHDRAWS", "rbi_register", entry.quote,
                  evidence_url=register_url)

    report = {
        "nodes": dict(Counter(data["type"] for _, data in graph.nodes(data=True))),
        "edges": edge_counts(graph),
        "failures": dict(failures),
    }
    return graph, report


def _sentence(text: str, position: int) -> str:
    """The sentence (or line) around ``position``: an exact substring of ``text``."""
    start = max(text.rfind("\n", 0, position), text.rfind(". ", 0, position) + 1, 0)
    ends = [index for index in (text.find("\n", position), text.find(". ", position)) if index != -1]
    return text[start:min(ends) + 1 if ends else len(text)].strip()


def _references(graph, node: str, text: str, provisions: dict, by_number: dict, document_id: str, failures: Counter,
                amending: bool = False) -> None:
    for match in _PARAGRAPH_REF.finditer(text):
        if _EXTERNAL.match(text, match.end()):
            continue  # "paragraph 5 of the Master Direction on KYC": another document's paragraph
        if amending:
            # "Paragraph 137 shall be deleted": an amendment's paragraph numbers are the amended document's.
            failures["paragraph_reference_in_amendment"] += 1
            continue
        for label in [match.group(1)] + re.findall(r"\d{1,3}", match.group(2) or ""):
            target = provisions.get(label)
            if target and target != node:
                _edge(graph, node, target, "REFERS_TO", "pattern", _sentence(text, match.start()))
            elif not target:
                failures["cross_reference_to_missing_paragraph"] += 1
    for reference in find_references(text):
        target = by_number.get(reference.key)
        if target and target != document_id:
            _edge(graph, node, target, "REFERS_TO", "pattern", _sentence(text, reference.start))
        elif not target:
            failures["reference_to_document_outside_corpus"] += 1


def add_llm_edges(graph: nx.MultiDiGraph, extraction: dict) -> dict:
    """APPLIES_TO (Provision -> RegulatedEntity | Product) and REQUIRES (Provision -> Obligation) from a saved,
    already validated extraction. Returns the counts of what was dropped and why."""
    from app.graph.llm_extraction import load_entities

    entities = load_entities()
    dropped: Counter = Counter()
    for provision, result in extraction["provisions"].items():
        if provision not in graph:
            dropped["provision_not_in_graph"] += 1
            continue
        dropped.update(result.get("dropped", {}))
        if result.get("error"):
            dropped[f"call_failed:{result['error'][:40]}"] += 1
        for number, edge in enumerate(result.get("edges", [])):
            entity = edge["entity"]
            graph.add_node(f"entity:{entity}", type=entities[entity]["type"], title=entities[entity]["name"])
            if edge["type"] == "APPLIES_TO":
                # Decision 6 (22 Oct 2026): the model over-lists entities (precision 24/67 on Ashu's labels).
                # Keep an edge only if the provision or its document's title names the entity.
                title = graph.nodes[graph.nodes[provision]["document_id"]]["title"]
                if not (names(entities[entity], graph.nodes[provision]["text"]) or names(entities[entity], title)):
                    dropped["APPLIES_TO:not_named_in_provision_or_title"] += 1
                    continue
                _edge(graph, provision, f"entity:{entity}", "APPLIES_TO", "llm", edge["quote"], confidence=edge["confidence"])
            else:
                obligation = f"{provision}/obligation:{number}"
                graph.add_node(obligation, type="Obligation", title=edge["obligation"], bearer=entity)
                _edge(graph, provision, obligation, "REQUIRES", "llm", edge["quote"], confidence=edge["confidence"])
    return {"model": extraction.get("model"), "dropped": dict(dropped)}


def names(entity: dict, text: str) -> bool:
    """Whether ``text`` mentions the entity by its name or an alias (whole words, case and punctuation ignored)."""
    from app.graph.llm_extraction import _key

    haystack = f" {_key(text)} "
    return any(f" {_key(alias)} " in haystack for alias in [entity["name"], *entity["aliases"]] if _key(alias))


def edge_counts(graph: nx.MultiDiGraph) -> dict:
    return dict(Counter(data["type"] for _, _, data in graph.edges(data=True)))


def neighbours(graph: nx.MultiDiGraph, node: str, edge_type: str, reverse: bool = False) -> list[str]:
    """Nodes one ``edge_type`` edge away from ``node`` (``reverse``: edges pointing at it)."""
    edges = graph.in_edges(node, data=True) if reverse else graph.out_edges(node, data=True)
    return sorted({(source if reverse else target) for source, target, data in edges if data["type"] == edge_type})


def add_layout(graph: nx.MultiDiGraph, seed: int = 7) -> None:
    """Precomputed positions (ForceAtlas2) and communities (Louvain) for the map."""
    simple = nx.Graph(graph.to_undirected())
    positions = nx.forceatlas2_layout(simple, max_iter=200, seed=seed)
    for number, community in enumerate(nx.community.louvain_communities(simple, seed=seed)):
        for node in community:
            graph.nodes[node]["community"] = number
    for node, (x, y) in positions.items():
        graph.nodes[node]["x"], graph.nodes[node]["y"] = round(float(x), 3), round(float(y), 3)


def save(graph: nx.MultiDiGraph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nx.node_link_data(graph, edges="edges"), ensure_ascii=False), encoding="utf-8")


def load(path: Path) -> nx.MultiDiGraph:
    return nx.node_link_graph(json.loads(path.read_text(encoding="utf-8")), edges="edges", multigraph=True, directed=True)
