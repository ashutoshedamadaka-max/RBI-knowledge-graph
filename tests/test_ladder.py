"""Phase 3 ladder pieces that need no model: BM25, rank fusion, nDCG and the one-change rule."""

import importlib.util
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")  # evaluation-only dependency (requirements-eval.txt)
from app.evaluation.ladder import BM25, ndcg_at, rrf  # noqa: E402

URL = "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=1"


def test_bm25_prefers_the_rarer_matching_term_and_ignores_footnote_markers() -> None:
    texts = ["Penal charges shall not be capitalised.[^2]", "The NBFC shall publish its loan policy.",
             "The NBFC shall review the policy every year."]
    bm25 = BM25(texts)

    assert bm25.rank("penal charges capitalised")[0] == 0
    assert bm25.rank("NBFC publish")[0] == 1  # "publish" is rarer than "NBFC"
    assert bm25.rank("unrelated words") == []


def test_reciprocal_rank_fusion_rewards_agreement() -> None:
    assert rrf([1, 2, 3], [3, 1, 2])[0] == 1  # ranked 1st and 2nd beats 3rd and 1st
    assert set(rrf([1], [2])) == {1, 2}


def test_ndcg_counts_each_gold_sentence_once() -> None:
    gold = [{"url": URL, "span": "Penal charges shall not be capitalised."}]
    hit = (URL, "B. Penal charges\n9. Penal charges shall not be capitalised.")

    assert ndcg_at([hit], gold) == 1.0
    assert ndcg_at([(URL, "other"), hit, hit], gold) == pytest.approx(1 / np.log2(3))
    assert ndcg_at([("https://www.rbi.org.in/other", hit[1])], gold) == 0.0  # right words, wrong page


def test_every_ladder_rung_changes_exactly_one_setting() -> None:
    spec = importlib.util.spec_from_file_location("run_ladder", Path(__file__).parents[1] / "scripts" / "run_ladder.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module.configs()

    for name, parent, _ in module.RUNGS:
        if parent:
            assert sum(plan[name][key] != plan[parent][key] for key in plan[name]) == 1, name


def test_graph_expansion_adds_cited_paragraphs_right_after_the_top_results() -> None:
    from types import SimpleNamespace

    import networkx as nx

    from app.evaluation.ladder import GraphExpansion

    chunks = [SimpleNamespace(document_id="d", text=text) for text in
              ["1. Lenders shall follow paragraph 3.", "2. Unrelated.", "3. The cited rule on penal charges."]]
    graph = nx.MultiDiGraph()
    for label, text in [("1", chunks[0].text), ("3", chunks[2].text)]:
        graph.add_node(f"d#{label}", type="Provision", document_id="d", text=text)
    graph.add_edge("d#1", "d#3", type="REFERS_TO")

    assert GraphExpansion(graph, chunks, head=1)([0, 1, 2]) == [0, 2, 1]
    assert GraphExpansion(graph, chunks, head=1)([1, 0, 2]) == [1, 0, 2]  # nothing cited by the top result
