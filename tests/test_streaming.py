from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest

from vectornote.generation import (
    OllamaClient,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaUnavailableError,
)
from vectornote.generation.streaming import NotFoundGate, ThinkFilter

# ---- ThinkFilter ------------------------------------------------------------


def _run_filter(chunks: list[str]) -> str:
    stripper = ThinkFilter()
    return "".join(stripper.feed(chunk) for chunk in chunks) + stripper.finish()


def _every_split(text: str) -> Iterator[list[str]]:
    yield list(text)  # one character at a time
    for cut in range(len(text) + 1):
        yield [text[:cut], text[cut:]]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<think>reasoning here</think>\nHello world", "Hello world"),
        ("<think>a</think><think>b</think>Answer", "Answer"),
        ("Before <think>hidden</think> after", "Before  after"),
        ("No tags at all", "No tags at all"),
        ("1 < 2 and 3 > 2", "1 < 2 and 3 > 2"),
        ("Use <thing> or <think", "Use <thing> or <think"),
    ],
)
def test_think_filter_is_independent_of_chunk_boundaries(text: str, expected: str) -> None:
    for chunks in _every_split(text):
        assert _run_filter(chunks) == expected, chunks


def test_unclosed_think_block_is_dropped() -> None:
    assert _run_filter(["<think>never ends", " and ends not"]) == ""


# ---- NotFoundGate -----------------------------------------------------------


def _run_gate(chunks: list[str]) -> list[str]:
    gate = NotFoundGate()
    out = [gate.feed(chunk) for chunk in chunks]
    out.append(gate.finish())
    return [piece for piece in out if piece]


def test_marker_is_never_shown() -> None:
    assert _run_gate(["NOT", "_FOUND"]) == []
    assert _run_gate(["not_found", " - the passages say nothing", " about it"]) == []
    assert _run_gate(["  \n", "NOT_FOUND"]) == []


def test_normal_answers_stream_through_after_the_first_pieces() -> None:
    assert _run_gate(["A ", "mutex ", "locks."]) == ["A ", "mutex ", "locks."]


def test_leading_whitespace_is_dropped() -> None:
    assert _run_gate(["  \n", "A mutex"]) == ["A mutex"]


def test_answers_that_start_like_the_marker_are_released_once_clear() -> None:
    assert "".join(_run_gate(["No", ", the ", "mutex locks"])) == "No, the mutex locks"
    assert "".join(_run_gate(["NOT", " a problem"])) == "NOT a problem"


def test_short_reply_that_stays_undecided_is_released_at_the_end() -> None:
    assert _run_gate(["NOT"]) == ["NOT"]


# ---- OllamaClient.stream ----------------------------------------------------


def _ndjson(*contents: str, done: bool = True) -> bytes:
    lines = [{"message": {"role": "assistant", "content": c}, "done": False} for c in contents]
    if done:
        lines.append({"message": {"role": "assistant", "content": ""}, "done": True})
    return ("\n".join(json.dumps(line) for line in lines) + "\n").encode()


def _client(handler: httpx.MockTransport) -> OllamaClient:
    return OllamaClient("http://ollama.test:11434", "llama3.2:3b", transport=handler)


def test_stream_yields_pieces_in_order_and_requests_streaming() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_ndjson("A ", "mutex ", "[1]."))

    pieces = list(_client(httpx.MockTransport(handler)).stream([{"role": "user", "content": "hi"}]))
    assert pieces == ["A ", "mutex ", "[1]."]
    payload = json.loads(seen[0].content)
    assert payload["stream"] is True
    assert payload["options"] == {"temperature": 0.1, "num_ctx": 4096}
    assert str(seen[0].url) == "http://ollama.test:11434/api/chat"


def test_stream_removes_reasoning_blocks_split_across_lines() -> None:
    body = _ndjson("<thi", "nk>pondering", "</th", "ink>\n", "Answer ", "[1]")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    assert "".join(_client(transport).stream([])) == "Answer [1]"


def test_stream_is_lazy() -> None:
    called: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(True)
        return httpx.Response(200, content=_ndjson("x"))

    stream = _client(httpx.MockTransport(handler)).stream([])
    assert called == []
    next(stream)
    assert called == [True]


def test_stream_reports_a_missing_model() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "nope"}))
    with pytest.raises(OllamaModelNotFoundError, match="ollama pull llama3.2:3b"):
        list(_client(transport).stream([]))


def test_stream_reports_an_unreachable_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailableError, match="ollama serve"):
        list(_client(httpx.MockTransport(handler)).stream([]))


def test_stream_reports_server_errors() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(OllamaError, match="HTTP 500"):
        list(_client(transport).stream([]))


def test_stream_reports_an_error_sent_midway() -> None:
    body = _ndjson("Partial ", done=False) + b'{"error": "model runner crashed"}\n'
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    stream = _client(transport).stream([])
    assert next(stream) == "Partial "
    with pytest.raises(OllamaError, match="model runner crashed"):
        next(stream)


class _TrackedBody(httpx.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self._body.splitlines(keepends=True)

    def close(self) -> None:
        self.closed = True


def test_closing_the_stream_early_closes_the_connection() -> None:
    body = _TrackedBody(_ndjson("one ", "two ", "three"))
    transport = httpx.MockTransport(lambda r: httpx.Response(200, stream=body))
    stream = _client(transport).stream([])
    assert next(stream) == "one "
    assert not body.closed
    stream.close()
    assert body.closed
