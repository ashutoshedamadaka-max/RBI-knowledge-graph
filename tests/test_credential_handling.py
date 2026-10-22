import logging
import traceback
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.llm.generation import AnswerGenerationError, OpenAIAnswerGenerator
from app.models.chunks import ChunkMetadata
from app.observability.errors import log_failure
from app.retrieval import pipeline


TOKEN = "credential-marker-for-test"


@pytest.mark.parametrize("field", ["openai_api_key", "cohere_api_key"])
def test_provider_keys_trim_pasted_whitespace_and_hide_repr(field):
    settings = Settings(_env_file=None, **{field: f" \t{TOKEN}\r\n"})
    assert getattr(settings, field) == TOKEN
    assert TOKEN not in repr(settings)


@pytest.mark.parametrize("field", ["openai_api_key", "cohere_api_key"])
def test_provider_keys_reject_embedded_whitespace_without_disclosing_input(field):
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **{field: f"{TOKEN}\nsecond-line"})
    assert TOKEN not in str(caught.value)
    assert "single token" in str(caught.value)


def test_failure_log_keeps_status_without_headers_or_traceback(caplog):
    request = httpx.Request("POST", "https://provider.invalid", headers={"Authorization": f"Bearer {TOKEN}"})
    error = httpx.HTTPStatusError(TOKEN, request=request, response=httpx.Response(401, request=request))
    log_failure(logging.getLogger(__name__), "provider_failed", error)
    assert "error_type=HTTPStatusError status_code=401" in caplog.text
    assert TOKEN not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_generation_failure_does_not_chain_credential_exception(monkeypatch, caplog):
    monkeypatch.setattr("app.llm.generation.httpx.post", Mock(side_effect=httpx.LocalProtocolError(TOKEN)))
    chunk = ChunkMetadata(chunk_id="c", document_id="d", document_title="Directions", page_number=1,
                          chunk_index=0, text="Disclose charges.")
    generator = OpenAIAnswerGenerator(TOKEN, "test-model", 0.15, 0.60, 12, 450)
    with pytest.raises(AnswerGenerationError) as caught:
        generator.generate("What must be disclosed?", [chunk])
    assert TOKEN not in "".join(traceback.format_exception(caught.value))
    assert TOKEN not in caplog.text
    assert "answer_generation_failed error_type=LocalProtocolError" in caplog.text


def test_dense_build_failure_logs_safe_metadata(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(pipeline, "_INDEXES", {})
    monkeypatch.setattr(pipeline, "corpus_embeddings", Mock(side_effect=httpx.LocalProtocolError(TOKEN)))
    retriever = pipeline.ApprovedRetriever(Settings(_env_file=None, data_dir=tmp_path, openai_api_key=TOKEN), None)
    _, dense, _ = retriever._build([{"chunk_id": "build-safety-test", "text": "loan repayment"}])
    assert dense is None
    assert "dense_index_unavailable error_type=LocalProtocolError" in caplog.text
    assert TOKEN not in caplog.text


def test_query_and_rerank_failures_preserve_results_without_logging_headers(monkeypatch, tmp_path, caplog):
    row = ChunkMetadata(chunk_id="c", document_id="d", document_title="Directions", page_number=1,
                        chunk_index=0, text="loan repayment limit", lifecycle="ACTIVE", authority_current=True).model_dump(mode="json")
    settings = Settings(_env_file=None, data_dir=tmp_path, openai_api_key=TOKEN, cohere_api_key=TOKEN)
    retriever = pipeline.ApprovedRetriever(settings, SimpleNamespace(_rows=lambda: [{"chunk": row}]))
    dense = SimpleNamespace(rank=Mock(side_effect=httpx.LocalProtocolError(TOKEN)))
    monkeypatch.setattr(retriever, "_build", lambda rows: (pipeline.BM25([row["text"]]), dense, None))
    monkeypatch.setattr(pipeline.CohereReranker, "rerank", Mock(side_effect=httpx.LocalProtocolError(TOKEN)))
    result = retriever.search("loan repayment", date(2026, 10, 22), 5)
    assert [item.chunk_id for item in result.results] == ["c"]
    assert result.top_score is None
    assert "dense_query_failed error_type=LocalProtocolError" in caplog.text
    assert "rerank_failed error_type=LocalProtocolError" in caplog.text
    assert TOKEN not in caplog.text
