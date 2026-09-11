from unittest.mock import Mock, patch

import httpx
import pytest

from app.llm.generation import AnswerGenerationError, OpenAIAnswerGenerator
from app.models.chunks import ChunkMetadata


def evidence() -> list[ChunkMetadata]:
    return [ChunkMetadata(
        chunk_id="chunk_0123456789abcdef0123",
        document_id="doc_0123456789abcdef0123",
        document_title="RBI Directions",
        source_url="https://www.rbi.org.in/example",
        page_number=1,
        chunk_index=0,
        text="A regulated entity must disclose applicable charges.",
    )]


def generator() -> OpenAIAnswerGenerator:
    return OpenAIAnswerGenerator("test-key", "gpt-4o-mini", 0.15, 0.60, 12, 450)


def test_openai_generator_limits_output_and_tracks_usage() -> None:
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": "### Answer\nDisclose charges. [chunk_0123456789abcdef0123]"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 25},
    }
    with patch("app.llm.generation.httpx.post", return_value=response) as post:
        result = generator().generate("What must be disclosed?", evidence())

    assert result.input_tokens == 100
    assert result.output_tokens == 25
    assert result.model == "gpt-4o-mini"
    assert post.call_args.kwargs["timeout"] == 12
    assert post.call_args.kwargs["json"]["max_tokens"] == 450
    assert "test-key" not in post.call_args.kwargs["json"]


def test_openai_generator_returns_safe_error_for_provider_failure() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    with patch("app.llm.generation.httpx.post", side_effect=httpx.HTTPStatusError("rate limited", request=request, response=response)):
        with pytest.raises(AnswerGenerationError, match="temporarily unavailable"):
            generator().generate("What must be disclosed?", evidence())
