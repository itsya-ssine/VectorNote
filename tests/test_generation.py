from __future__ import annotations

import json

import httpx
import pytest

from vectornote.generation import (
    OllamaClient,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaUnavailableError,
)
from vectornote.generation.citations import extract_citations, is_not_found
from vectornote.generation.prompts import (
    MAX_CONTEXT_CHARS,
    NOT_FOUND,
    SYSTEM_PROMPT,
    build_messages,
    refusal_message,
    select_context,
)
from vectornote.models import Chunk, SearchResult


def _result(number: int, text: str = "some text", source: str = "os.pdf") -> SearchResult:
    chunk = Chunk(chunk_id=f"c{number}", source=source, page=number, text=text)
    return SearchResult(chunk=chunk, score=0.5)


# ---- citations --------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("A mutex locks [1]. Semaphores count [2].", [1, 2]),
        ("Both are covered [2][1].", [2, 1]),
        ("Combined claim [1, 3].", [1, 3]),
        ("Combined claim [1; 2].", [1, 2]),
        ("Repeated [1] and again [1].", [1]),
        ("Invented source [9] and [0].", []),
        ("No citation at all.", []),
        ("An array a[1] is not a citation? It is, to the parser: [1].", [1]),
    ],
)
def test_extract_citations(answer: str, expected: list[int]) -> None:
    assert extract_citations(answer, passage_count=3) == expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (NOT_FOUND, True),
        ("  not_found\n", True),
        ("NOT_FOUND - the passages do not say", True),
        ("The answer is in the NOT_FOUND section", False),
        ("A mutex [1]", False),
    ],
)
def test_is_not_found(answer: str, expected: bool) -> None:
    assert is_not_found(answer) is expected


# ---- prompts ----------------------------------------------------------------


def test_build_messages_numbers_the_passages_and_ends_with_the_question() -> None:
    context = [_result(1, "Mutexes lock."), _result(2, "Semaphores count.", source="net.md")]
    system, user = build_messages("  What is a mutex? ", context)
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    body = user["content"]
    assert "[1] os.pdf, page 1\nMutexes lock." in body
    assert "[2] net.md, page 2\nSemaphores count." in body
    assert body.index("[1]") < body.index("[2]")
    assert body.endswith("Question: What is a mutex?")


def test_system_prompt_states_the_rules() -> None:
    assert "ONLY" in SYSTEM_PROMPT
    assert NOT_FOUND in SYSTEM_PROMPT
    assert "square brackets" in SYSTEM_PROMPT
    assert "same language" in SYSTEM_PROMPT


def test_select_context_respects_the_budget_but_keeps_one_passage() -> None:
    big = "x" * (MAX_CONTEXT_CHARS - 10)
    results = [_result(1, big), _result(2, "y" * 100), _result(3, "z")]
    assert [r.chunk.chunk_id for r in select_context(results)] == ["c1"]
    huge = [_result(1, "x" * (MAX_CONTEXT_CHARS * 2)), _result(2, "short")]
    assert [r.chunk.chunk_id for r in select_context(huge)] == ["c1"]
    small = [_result(1, "a"), _result(2, "b")]
    assert len(select_context(small)) == 2


def test_refusal_message_follows_the_language_of_the_question() -> None:
    assert refusal_message("What is the difference between TCP and UDP?").startswith("I couldn't")
    assert refusal_message("Quelle est la différence entre TCP et UDP ?").startswith("Je n'ai pas")
    assert "vide" in refusal_message("Comment fonctionne la pagination ?", "empty_index")
    assert "empty" in refusal_message("How does paging work?", "empty_index")
    assert refusal_message("Comment").startswith("I couldn't")  # one marker is not enough


# ---- Ollama client ----------------------------------------------------------


def _client(handler: httpx.MockTransport) -> OllamaClient:
    return OllamaClient("http://ollama.test:11434/", "llama3.2:3b", transport=handler)


def test_complete_sends_the_conversation_and_strips_reasoning() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        content = "<think>hmm</think>\nA mutex [1]."
        return httpx.Response(200, json={"message": {"content": content}})

    reply = _client(httpx.MockTransport(handler)).complete([{"role": "user", "content": "hi"}])
    assert reply == "A mutex [1]."
    request = seen[0]
    assert str(request.url) == "http://ollama.test:11434/api/chat"
    payload = json.loads(request.content)
    assert payload["model"] == "llama3.2:3b"
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    assert payload["options"] == {"temperature": 0.1, "num_ctx": 4096}


def test_chat_wraps_a_single_prompt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["messages"] == [{"role": "user", "content": "hello"}]
        return httpx.Response(200, json={"message": {"content": "hi"}})

    assert _client(httpx.MockTransport(handler)).chat("hello") == "hi"


def test_missing_model_tells_you_how_to_install_it() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "not found"}))
    with pytest.raises(OllamaModelNotFoundError, match="ollama pull llama3.2:3b"):
        _client(transport).chat("hi")


def test_unreachable_server_is_reported_clearly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(OllamaUnavailableError, match="ollama serve"):
        _client(httpx.MockTransport(handler)).chat("hi")


def test_timeout_is_reported_clearly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(OllamaUnavailableError, match="did not answer"):
        _client(httpx.MockTransport(handler)).chat("hi")


def test_server_errors_become_ollama_errors() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(OllamaError, match="HTTP 500"):
        _client(transport).chat("hi")
