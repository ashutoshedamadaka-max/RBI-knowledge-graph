"""Streaming the answer: the direct answer's text is read from JSON still being written."""

import json
from contextlib import contextmanager
from unittest.mock import patch

from app.llm.generation import _stream_chat, partial_direct_answer

HEAD = '{"status":"grounded","display_title":"Penal charges","direct_answer":{"title":null,"text":"'


def test_the_direct_answer_is_read_from_a_partial_json_answer() -> None:
    assert partial_direct_answer('{"status":"grounded"') is None
    assert partial_direct_answer(HEAD + 'No. Penal \\"charges') == 'No. Penal "charges'
    assert partial_direct_answer(HEAD + "Line one\\nline two\\") == "Line one\nline two"  # stopped mid-escape
    assert partial_direct_answer(HEAD + "Caf\\u00") == "Caf"  # stopped inside a unicode escape
    assert partial_direct_answer(HEAD + 'Done.","citation_ids":["c1"]},') == "Done."


def test_a_streamed_answer_returns_the_same_shape_as_a_normal_one() -> None:
    final = {"status": "grounded", "display_title": None, "direct_answer": {"title": None, "text": "No.", "citation_ids": []},
             "sections": [], "related_questions": []}
    text = json.dumps(final)
    pieces = [text[:60], text[60:]]
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}" for piece in pieces]
    lines += [f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}",
              f"data: {json.dumps({'choices': [], 'usage': {'prompt_tokens': 9, 'completion_tokens': 3}})}", "data: [DONE]"]

    class Response:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(lines)

    @contextmanager
    def fake_stream(*args, **kwargs):
        assert kwargs["json"]["stream"] is True
        yield Response()

    seen = []
    with patch("app.llm.generation.httpx.stream", fake_stream):
        body = _stream_chat("k", {"model": "m"}, 10, seen.append)

    assert json.loads(body["choices"][0]["message"]["content"]) == final
    assert body["choices"][0]["finish_reason"] == "stop" and body["usage"]["completion_tokens"] == 3
    assert seen and seen[-1] == "No."
