import json
import re
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel

from app.config.settings import Settings
from app.models.chunks import ChunkMetadata
from app.models.research import ResearchClaim, ResearchSection, ResearchStatus, StructuredResearch


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
    def generate(self, query: str, evidence: list[ChunkMetadata]) -> GenerationResult:
        raise NotImplementedError


def research_to_markdown(research: StructuredResearch) -> str:
    if research.status is ResearchStatus.INSUFFICIENT_EVIDENCE:
        return "### Insufficient evidence\nI could not find enough RBI lending evidence in the indexed corpus to answer this responsibly."
    parts = []
    if research.direct_answer:
        citations = " ".join(f"[{item}]" for item in research.direct_answer.citation_ids)
        parts.extend(["### Direct answer", f"{research.direct_answer.text} {citations}".strip()])
    for section in research.sections:
        parts.append(f"### {section.title}")
        for claim in section.claims:
            citations = " ".join(f"[{item}]" for item in claim.citation_ids)
            parts.append(f"- {claim.text} {citations}".strip())
    return "\n\n".join(parts)


def _query_terms(query: str) -> set[str]:
    ignored = {"about", "and", "are", "can", "does", "for", "from", "how", "must", "of", "on", "or", "rbi", "the", "to", "under", "what", "when", "which", "with"}
    return {term for term in re.findall(r"[a-z0-9]{3,}", query.lower()) if term not in ignored}


def _clean_sentence(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = re.sub(r"^Chapter [IVXLC]+:\s*", "", sentence, flags=re.IGNORECASE)
    sentence = re.sub(r"^\d+\.\s+[^.]+?\s+(?=[ivxlcdm]+\.\s)", "", sentence, flags=re.IGNORECASE)
    return re.sub(r"^[ivxlcdm]+\.\s+", "", sentence, flags=re.IGNORECASE)


def _relevant_sentences(query: str, evidence: list[ChunkMetadata]) -> list[tuple[ChunkMetadata, str]]:
    """Select concise source sentences when an LLM response cannot be used safely."""
    terms = _query_terms(query)
    candidates: list[tuple[float, int, ChunkMetadata, str]] = []
    for evidence_order, chunk in enumerate(evidence):
        title_terms = set(re.findall(r"[a-z0-9]{3,}", chunk.document_title.lower()))
        for sentence in re.split(r"(?<=[.!?])\s+", chunk.text):
            cleaned = _clean_sentence(sentence)
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


class DeterministicAnswerGenerator(AnswerGenerator):
    """Evidence-only response composer used when no model is configured."""

    def generate(self, query: str, evidence: list[ChunkMetadata]) -> GenerationResult:
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

    def generate(self, query: str, evidence: list[ChunkMetadata]) -> GenerationResult:
        context = "\n\n".join(
            f"CHUNK {chunk.chunk_id} | {chunk.document_title} | page {chunk.page_number}\n{chunk.text}"
            for chunk in evidence
        )
        prompt = (
            "Return JSON only. Answer using only the provided RBI evidence. Do not invent regulations, dates, "
            "or legal requirements. Use status 'insufficient_evidence' when the evidence cannot support a direct answer. "
            "For a grounded answer, direct_answer and every claim must include citation_ids containing only supplied chunk IDs. "
            "Use only meaningful sections; do not create empty sections. related_questions is optional and must be RBI lending questions.\n"
            "JSON shape: {status, direct_answer:{text,citation_ids}|null, sections:[{id,title,claims:[{text,citation_ids}]}], related_questions:[...]}.\n\n"
            f"QUESTION: {query}\n\nEVIDENCE:\n{context}"
        )
        try:
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Grounded regulatory assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": self.max_output_tokens,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AnswerGenerationError(
                "The AI answer service is temporarily unavailable. Please retry in a moment."
            ) from exc
        body = response.json()
        usage = body.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        from app.observability.costs import estimate_openai_cost
        content = body["choices"][0]["message"]["content"]
        try:
            research = StructuredResearch.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValueError):
            research = None
        return GenerationResult(
            answer=research_to_markdown(research) if research else content,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimate_openai_cost(input_tokens, output_tokens, self.input_rate, self.output_rate),
            research=research,
        )


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
