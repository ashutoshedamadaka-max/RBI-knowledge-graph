import json
from abc import ABC, abstractmethod

import httpx

from app.config.settings import Settings
from app.models.chunks import ChunkMetadata


class AnswerGenerator(ABC):
    @abstractmethod
    def generate(self, query: str, evidence: list[ChunkMetadata]) -> str:
        raise NotImplementedError


class DeterministicAnswerGenerator(AnswerGenerator):
    """Evidence-only response composer used when no model is configured."""

    def generate(self, query: str, evidence: list[ChunkMetadata]) -> str:
        if not evidence:
            return (
                "### Answer\n"
                "I do not have sufficient retrieved RBI evidence to answer this question.\n\n"
                "### Regulatory basis\nNo relevant source chunk was retrieved."
            )
        lines = [
            "### Answer",
            "The retrieved RBI material provides the following directly relevant evidence:",
        ]
        for chunk in evidence:
            text = chunk.text.replace("\n", " ").strip()
            lines.append(f"- {text[:700]} [{chunk.chunk_id}]")
        lines.extend(["", "### Regulatory basis", "Each statement above is quoted or condensed from the cited retrieved chunk."])
        return "\n".join(lines)


class OpenAIAnswerGenerator(AnswerGenerator):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, query: str, evidence: list[ChunkMetadata]) -> str:
        context = "\n\n".join(
            f"CHUNK {chunk.chunk_id} | {chunk.document_title} | page {chunk.page_number}\n{chunk.text}"
            for chunk in evidence
        )
        prompt = (
            "Answer using only the provided RBI evidence. Do not invent regulations, dates, or legal requirements. "
            "If evidence is insufficient, say so. Cite every material regulatory claim using only [chunk_id] "
            "from the evidence. Do not cite a chunk not provided.\n\n"
            f"QUESTION: {query}\n\nEVIDENCE:\n{context}"
        )
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": [{"role": "system", "content": "Grounded regulatory assistant."}, {"role": "user", "content": prompt}], "temperature": 0},
            timeout=45,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def get_answer_generator(settings: Settings) -> AnswerGenerator:
    if settings.answer_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when ANSWER_PROVIDER=openai.")
        return OpenAIAnswerGenerator(settings.openai_api_key, settings.openai_answer_model)
    return DeterministicAnswerGenerator()

