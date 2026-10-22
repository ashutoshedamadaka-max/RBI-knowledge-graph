import json
import logging
import re
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel

from app.config.settings import Settings
from app.models.chunks import ChunkMetadata
from app.models.research import ResearchClaim, ResearchSection, ResearchStatus, StructuredResearch

logger = logging.getLogger(__name__)


def answer_output_schema() -> dict:
    """Constrain model output to the UI contract, not merely valid JSON."""
    def obj(properties):
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}
    claim = obj({"title": {"type": ["string", "null"], "maxLength": 120}, "text": {"type": "string", "minLength": 1, "maxLength": 1800},
                 "citation_ids": {"type": "array", "items": {"type": "string"}}})
    section = obj({"id": {"type": "string", "pattern": "^[a-z0-9-]+$"}, "title": {"type": "string", "minLength": 1, "maxLength": 100},
                   "claims": {"type": "array", "items": claim, "maxItems": 8}})
    return obj({"status": {"type": "string", "enum": ["grounded", "insufficient_evidence"]},
                "display_title": {"type": ["string", "null"], "maxLength": 140},
                "direct_answer": {"anyOf": [claim, {"type": "null"}]},
                "sections": {"type": "array", "items": section, "maxItems": 6},
                "related_questions": {"type": "array", "items": {"type": "string"}, "maxItems": 3}})


class GenerationResult(BaseModel):
    answer: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    research: StructuredResearch | None = None


class AnswerGenerationError(RuntimeError):
    """A configured model provider could not produce a grounded answer."""


class AnswerGenerator(ABC):
    @abstractmethod
    def generate(self, query: str, evidence: list[ChunkMetadata],
                 sections: dict[str, str] | None = None, as_of=None, notices: list[str] | None = None,
                 on_text=None) -> GenerationResult:
        raise NotImplementedError


def align_research_headings(research: StructuredResearch, evidence: list[ChunkMetadata]) -> StructuredResearch:
    """Remove unsupported topic labels; this is not semantic claim verification.

    Headings are optional presentation metadata. Require their substantive words
    in both their own body and cited text rather than adding an ungrounded topic.
    Conservative false negatives simply result in an untitled, numbered provision.
    """
    ignored = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with",
               "key", "requirements", "requirement", "supporting", "provisions", "provision", "changes", "change", "rules", "rule", "modifications"}
    def terms(value: str) -> set[str]:
        return {word.rstrip("s") for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in ignored}
    chunks = {chunk.chunk_id: chunk.text for chunk in evidence}
    def supported(title: str, claims: list[ResearchClaim]) -> bool:
        heading_terms = terms(title)
        body = " ".join(claim.text for claim in claims)
        cited = " ".join(chunks.get(cid, "") for claim in claims for cid in claim.citation_ids)
        return not heading_terms or (heading_terms <= terms(body) and heading_terms <= terms(cited))
    sections = []
    for section in research.sections:
        claims = [claim.model_copy(update={"title": None}) if claim.title and not supported(claim.title, [claim]) else claim
                  for claim in section.claims]
        sections.append(section.model_copy(update={
            "claims": claims,
            "title": section.title if supported(section.title, claims) else "Supporting provisions",
        }))
    return research.model_copy(update={"sections": sections})


def research_to_markdown(research: StructuredResearch) -> str:
    if research.status is ResearchStatus.INSUFFICIENT_EVIDENCE:
        return "### Insufficient evidence\nI could not find enough RBI lending evidence in the indexed corpus to answer this responsibly."
    parts = []
    if research.direct_answer:
        citations = " ".join(f"[{item}]" for item in research.direct_answer.citation_ids)
        parts.extend(["### Direct answer", f"{research.direct_answer.text} {citations}{_flag(research.direct_answer)}".strip()])
    for section in research.sections:
        parts.append(f"### {section.title}")
        for claim in section.claims:
            citations = " ".join(f"[{item}]" for item in claim.citation_ids)
            parts.append(f"- {claim.text} {citations}{_flag(claim)}".strip())
    return "\n\n".join(parts)


FLAGS = {"partially_supported": " _(only partly supported by the cited text)_",
         "not_supported": " _(not supported by the cited text)_"}


def _flag(claim: ResearchClaim) -> str:
    """ADR-030: a claim the checker does not pass is shown with a marker, never silently kept or rewritten."""
    return FLAGS.get(claim.support or "", "")


def _query_terms(query: str) -> set[str]:
    ignored = {"about", "and", "are", "can", "does", "for", "from", "how", "must", "of", "on", "or", "rbi", "require", "required", "requirement", "requirements", "the", "to", "under", "what", "when", "which", "with"}
    return {term for term in re.findall(r"[a-z0-9]{3,}", query.lower()) if term not in ignored}


def _clean_sentence(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = re.sub(r"^Chapter [IVXLC]+:\s*", "", sentence, flags=re.IGNORECASE)
    sentence = re.sub(r"^\d+\.\s+[^.]+?\s+(?=[ivxlcdm]+\.\s)", "", sentence, flags=re.IGNORECASE)
    return re.sub(r"^[ivxlcdm]+\.\s+", "", sentence, flags=re.IGNORECASE)


def _relevant_sentences(query: str, evidence: list[ChunkMetadata]) -> list[tuple[ChunkMetadata, str]]:
    """Select concise source sentences when an LLM response cannot be used safely."""
    terms = _query_terms(query)
    # If every retrieved result has the same topic in its title, that topic helped retrieval
    # but should not overpower the question's remaining, more specific concept.
    if evidence:
        title_sets = [set(re.findall(r"[a-z0-9]{3,}", chunk.document_title.lower())) for chunk in evidence]
        common_title_terms = set.intersection(*title_sets)
        focused_terms = terms - common_title_terms
        if focused_terms:
            terms = focused_terms
    candidates: list[tuple[float, int, ChunkMetadata, str]] = []
    for evidence_order, chunk in enumerate(evidence):
        title_terms = set(re.findall(r"[a-z0-9]{3,}", chunk.document_title.lower()))
        for sentence in re.split(r"(?<=[.!?])\s+", chunk.text):
            cleaned = _clean_sentence(sentence)
            # Legacy indexed pages may still contain navigation. Never present it
            # as a regulatory provision, even when its topic words match.
            if re.search(r"skip to main content|not pressed|search the website|organisation structure|official website of reserve bank", cleaned, re.I):
                continue
            if len(cleaned) > 700 or re.search(r"\bas (?:below|follows)\s*:", cleaned, re.I):
                continue
            sentence_terms = set(re.findall(r"[a-z0-9]{3,}", cleaned.lower()))
            overlap = len(terms & sentence_terms)
            if len(cleaned) < 45 or overlap == 0:
                continue
            title_overlap = len(terms & title_terms)
            score = (2 * overlap) + (0.35 * title_overlap)
            candidates.append((score, evidence_order, chunk, cleaned[:700]))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    selected: list[tuple[ChunkMetadata, str]] = []
    seen: set[str] = set()
    for _, _, chunk, sentence in candidates:
        normalised = sentence.lower()
        if normalised in seen:
            continue
        selected.append((chunk, sentence))
        seen.add(normalised)
        if len(selected) == 3:
            break
    return selected


def deterministic_research(query: str, evidence: list[ChunkMetadata]) -> StructuredResearch:
    if not evidence:
        return StructuredResearch(status=ResearchStatus.INSUFFICIENT_EVIDENCE)
    selected = _relevant_sentences(query, evidence)
    if not selected:
        return StructuredResearch(status=ResearchStatus.INSUFFICIENT_EVIDENCE)
    lead_chunk, lead_sentence = selected[0]
    claims = [
        ResearchClaim(text=sentence, citation_ids=[chunk.chunk_id])
        for chunk, sentence in selected[1:]
    ]
    return StructuredResearch(
        status=ResearchStatus.GROUNDED,
        direct_answer=ResearchClaim(
            text=f"{lead_chunk.document_title} states: “{lead_sentence}”",
            citation_ids=[lead_chunk.chunk_id],
        ),
        sections=[ResearchSection(id="supporting-provisions", title="Supporting provisions", claims=claims)] if claims else [],
    )


def _status(chunk: ChunkMetadata, as_of) -> str:
    """How the answer step sees a passage: in force on the answer date (search already ensured it), and
    withdrawn since if it was. Today's status alone made the model refuse correct past-date answers."""
    lifecycle = chunk.lifecycle.value
    if as_of is None:
        return f"lifecycle {lifecycle}"
    return f"in force on {as_of}" + ("" if lifecycle in {"ACTIVE", "AMENDED"} else f" ({lifecycle.lower()} since)")


class DeterministicAnswerGenerator(AnswerGenerator):
    """Evidence-only response composer used when no model is configured."""

    def generate(self, query: str, evidence: list[ChunkMetadata],
                 sections: dict[str, str] | None = None, as_of=None, notices: list[str] | None = None,
                 on_text=None) -> GenerationResult:
        research = deterministic_research(query, evidence)
        return GenerationResult(answer=research_to_markdown(research), model="deterministic", research=research)


class OpenAIAnswerGenerator(AnswerGenerator):
    def __init__(
        self,
        api_key: str,
        model: str,
        input_rate: float,
        output_rate: float,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def generate(self, query: str, evidence: list[ChunkMetadata],
                 sections: dict[str, str] | None = None, as_of=None, notices: list[str] | None = None,
                 on_text=None) -> GenerationResult:
        context = "\n\n".join(
            f"CHUNK {chunk.chunk_id} | {chunk.document_title} | {_status(chunk, as_of)} | passage {chunk.chunk_index + 1}\n{chunk.text}"
            + (f"\nSECTION CONTEXT (to understand the passage; cite only the CHUNK id above):\n{sections[chunk.chunk_id]}"
               if sections and chunk.chunk_id in sections else "")
            for chunk in evidence
        )
        prompt = (
            "Return JSON only. Answer using only the provided RBI evidence. Do not invent regulations, dates, "
            "or legal requirements. Use status 'insufficient_evidence' only when no passage addresses the question; "
            "when passages answer part of it, answer that part and say what the evidence does not cover. "
            "For a grounded answer, direct_answer and every claim must include citation_ids containing only supplied chunk IDs. "
            "display_title should be a concise, factual answer heading. direct_answer should be a plain-English summary "
            "of the cited evidence in 2-3 short sentences, directly answering the question. "
            "For amendment questions explain each actual change, who it affects and its effective date only when supplied. "
            "A reference to another document or 'modified as below' is not the change itself. "
            "Ignore website navigation and boilerplate. Do not claim a before/after comparison unless both are supported. "
            "When only some requested amendments are supported, explain those and state the coverage limit; "
            "do not imply that the summary covers all amendments. Never present struck-out or deleted text as a current rule. "
            "citation_ids must contain bare supplied chunk IDs without square brackets. "
            "Each claim title should be scannable and factual. Use only meaningful sections; "
            "Keep the summary under 90 words and prefer at most 5 distinct requirements. Expand unfamiliar abbreviations. "
            "Every heading must describe its own claim: never label healthcare provisions as housing, or infer a category. "
            "Only include a heading if its wording is supported by both the claim and its cited passage; otherwise use null. "
            "Do not infer that a provision is new just because it appears in an amendment. "
            "Every passage supplied was in force on the answer date. When the answer date is in the past, answer with "
            "the rules in force then, and say so; a rule withdrawn since is still the correct answer for that date. "
            "do not create empty sections. related_questions is optional and must be RBI lending questions. "
            "Each claim states one requirement or fact and cites the passages that state it; never combine two "
            "requirements in one claim. If the question assumes something the evidence contradicts, the status is "
            "'grounded': correct the assumption plainly, citing the passage that shows it. "
            "When CHANGE NOTICES are given, state the relevant ones in the direct answer: a rule replaced or withdrawn "
            "since, or a rule that takes effect only from a future date (say that date).\n"
            "JSON shape: {status, display_title|null, direct_answer:{text,citation_ids}|null, "
            "sections:[{id,title,claims:[{title|null,text,citation_ids}]}], related_questions:[...]}.\n\n"
            + (f"ANSWER AS OF: {as_of} (use the rules in force on that date)\n" if as_of else "")
            + ("CHANGE NOTICES (facts from RBI's records):\n" + "\n".join(f"- {item}" for item in notices) + "\n" if notices else "")
            + f"QUESTION: {query}\n\nEVIDENCE:\n{context}"
        )
        try:
            request = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Grounded regulatory assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": self.max_output_tokens,
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "rbi_research_answer", "strict": True, "schema": answer_output_schema(),
                }},
            }
            if on_text:
                body = _stream_chat(self.api_key, request, self.timeout_seconds, on_text)
            else:
                response = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=request,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise AnswerGenerationError(
                "The AI answer service is temporarily unavailable. Please retry in a moment."
            ) from exc
        usage = body.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        from app.observability.costs import estimate_openai_cost
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length" or choice["message"].get("refusal"):
            raise AnswerGenerationError("The AI answer could not be completed safely. Please try a more specific question.")
        content = choice["message"]["content"]
        try:
            research = StructuredResearch.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValueError) as exc:
            issues = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]}
                      for item in exc.errors()] if hasattr(exc, "errors") else []
            logger.warning("structured_answer_invalid error_type=%s issues=%s", type(exc).__name__, issues)
            research = None
        return GenerationResult(
            answer=research_to_markdown(research) if research else content,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimate_openai_cost(input_tokens, output_tokens, self.input_rate, self.output_rate),
            research=research,
        )


_DIRECT_TEXT = re.compile(r'"direct_answer"\s*:\s*\{\s*"title"\s*:\s*(?:null|"(?:[^"\\]|\\.)*")\s*,\s*"text"\s*:\s*"((?:[^"\\]|\\.)*)')


def partial_direct_answer(content: str) -> str | None:
    """The direct answer's text so far, read from a JSON answer still being written (schema order puts it early)."""
    match = _DIRECT_TEXT.search(content)
    if not match:
        return None
    raw = match.group(1)
    for cut in range(0, 7):  # the stream may stop mid-escape, for example after a lone backslash or inside \\u00e9
        try:
            return json.loads(f'"{raw[:len(raw) - cut]}"')
        except json.JSONDecodeError:
            continue
    return None


def _stream_chat(api_key: str, request: dict, timeout: float, on_text) -> dict:
    """The same chat completion, streamed: on_text gets the direct answer's text as it grows. Returns a body in
    the shape of the non-streamed response, so the caller's checks (length, refusal, schema) are unchanged."""
    content, finish, refusal, usage, shown = "", None, None, {}, ""
    with httpx.stream("POST", "https://api.openai.com/v1/chat/completions", timeout=timeout,
                      headers={"Authorization": f"Bearer {api_key}"},
                      json={**request, "stream": True, "stream_options": {"include_usage": True}}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            usage = event.get("usage") or usage
            for choice in event.get("choices", []):
                delta = choice.get("delta", {})
                content += delta.get("content") or ""
                refusal = refusal or delta.get("refusal")
                finish = choice.get("finish_reason") or finish
            text = partial_direct_answer(content)
            if text and text != shown:
                shown = text
                on_text(text)
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "refusal": refusal}}], "usage": usage}


def get_answer_generator(settings: Settings) -> AnswerGenerator:
    if settings.answer_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when ANSWER_PROVIDER=openai.")
        return OpenAIAnswerGenerator(
            settings.openai_api_key,
            settings.openai_answer_model,
            settings.openai_input_cost_per_million,
            settings.openai_output_cost_per_million,
            settings.openai_timeout_seconds,
            settings.openai_max_output_tokens,
        )
    return DeterministicAnswerGenerator()
