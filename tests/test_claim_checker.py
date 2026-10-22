"""The Phase 5 claim checker's own rules, with the model call replaced by a canned verdict."""

import json
from unittest.mock import Mock, patch

from app.llm.claim_checker import check
from app.models.chunks import ChunkMetadata
from app.models.research import ResearchClaim, ResearchSection, ResearchStatus, StructuredResearch

PASSAGE = ChunkMetadata(chunk_id="chunk_a", document_id="d", document_title="RBC Directions", page_number=1, chunk_index=0,
                        text="9. Penal charges shall not be capitalised and no further interest shall be computed on them.")


def _research(*claims: ResearchClaim) -> StructuredResearch:
    return StructuredResearch(status=ResearchStatus.GROUNDED, direct_answer=claims[0],
                              sections=[ResearchSection(id="s", title="Rules", claims=list(claims[1:]))])


def _model_says(verdicts: list[dict]):
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": json.dumps({"verdicts": verdicts})}}],
                                  "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    return patch("app.llm.claim_checker.httpx.post", return_value=response)


def test_verdicts_follow_the_cited_passages_and_their_quotes() -> None:
    research = _research(
        ResearchClaim(text="Penal charges cannot be capitalised.", citation_ids=["chunk_a"]),
        ResearchClaim(text="No interest is computed on penal charges.", citation_ids=["chunk_a"]),
        ResearchClaim(text="Penal charges are capped at 2%.", citation_ids=[]),           # cites nothing
        ResearchClaim(text="Lenders must publish penal charges.", citation_ids=["chunk_a"]),  # the model skips it
    )
    with _model_says([
        {"claim": 1, "verdict": "supported", "quote": "Penal charges shall not be capitalised"},
        {"claim": 2, "verdict": "supported", "quote": "interest shall be waived"},  # not in the passage
    ]) as post:
        verdicts, usage = check("k", "m", research, [PASSAGE])

    assert [item["verdict"] for item in verdicts] == ["supported", "partially_supported", "not_supported", "not_supported"]
    assert verdicts[2]["reason"] == "no valid citation" and verdicts[3]["reason"] == "checker returned no verdict"
    prompt = post.call_args.kwargs["json"]["messages"][1]["content"]
    assert "CLAIM 3" not in prompt and "QUESTION" not in prompt  # uncited claims and the question are never sent
    assert usage["prompt_tokens"] == 10


def test_a_claim_with_no_citations_needs_no_model_call() -> None:
    with patch("app.llm.claim_checker.httpx.post") as post:
        verdicts, _ = check("k", "m", _research(ResearchClaim(text="A rule.", citation_ids=["chunk_unknown"])), [PASSAGE])

    assert verdicts == [{"verdict": "not_supported", "quote": "", "reason": "no valid citation"}]
    post.assert_not_called()


def test_claims_the_checker_does_not_pass_are_flagged_in_the_answer() -> None:
    from app.llm.claim_checker import with_verdicts
    from app.llm.generation import research_to_markdown

    research = with_verdicts(
        _research(ResearchClaim(text="Penal charges cannot be capitalised.", citation_ids=["chunk_a"]),
                  ResearchClaim(text="Penal charges are capped at 2%.", citation_ids=["chunk_a"])),
        [{"verdict": "supported"}, {"verdict": "partially_supported"}])

    text = research_to_markdown(research)
    assert "capitalised. [chunk_a]" in text and "capitalised. [chunk_a] _(" not in text  # supported: no marker
    assert "capped at 2%. [chunk_a] _(only partly supported by the cited text)_" in text
