from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vectornote.api.app import create_app
from vectornote.api.deps import get_service
from vectornote.cli import main
from vectornote.config import Settings
from vectornote.embeddings.hashing import HashingEmbedder
from vectornote.generation import OllamaUnavailableError
from vectornote.generation.prompts import NOT_FOUND
from vectornote.service import RagService

MUTEX = "A mutex gives mutual exclusion to a critical section."
SUBNET = "A subnet mask separates the network and host parts of an address."


class FakeLLM:
    """Records the conversations it receives and replies with a canned answer."""

    def __init__(self, reply: str = "A mutex gives mutual exclusion [1].") -> None:
        self.reply = reply
        self.error: Exception | None = None
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        self.calls.append([dict(m) for m in messages])
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        chroma_dir=tmp_path / "db",
        embedding_model="hashing",
    )


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(settings: Settings, llm: FakeLLM) -> RagService:
    return RagService(settings, embedder=HashingEmbedder(), llm=llm)


@pytest.fixture
def indexed(service: RagService, settings: Settings) -> RagService:
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "os.txt").write_text(MUTEX)
    (settings.data_dir / "net.txt").write_text(SUBNET)
    list(service.ingest_directory(settings.data_dir))
    return service


QUESTION = "How does a mutex protect a critical section?"


# ---- service ----------------------------------------------------------------


def test_grounded_answer_with_citations(indexed: RagService, llm: FakeLLM) -> None:
    result = indexed.ask(QUESTION)
    assert result.answered
    assert result.cited
    assert result.answer == "A mutex gives mutual exclusion [1]."
    assert [(c.number, c.source, c.page) for c in result.citations] == [(1, "os.txt", 1)]
    assert result.citations[0].snippet == MUTEX
    assert len(llm.calls) == 1


def test_the_model_receives_rules_numbered_passages_and_the_question(
    indexed: RagService, llm: FakeLLM
) -> None:
    indexed.ask(QUESTION)
    system, user = llm.calls[0]
    assert system["role"] == "system"
    assert NOT_FOUND in system["content"]
    assert "[1] os.txt, page 1\n" + MUTEX in user["content"]
    assert user["content"].endswith(f"Question: {QUESTION}")


def test_multiple_citations_are_all_returned(indexed: RagService, llm: FakeLLM) -> None:
    llm.reply = "Both matter [1][2]."
    result = indexed.ask("mutex critical section subnet mask address", top_k=2)
    assert [c.number for c in result.citations] == [1, 2]


def test_invented_citation_numbers_are_ignored(indexed: RagService, llm: FakeLLM) -> None:
    llm.reply = "A mutex locks [1] and also [7]."
    result = indexed.ask(QUESTION)
    assert [c.number for c in result.citations] == [1]
    assert result.cited


def test_answer_without_citations_falls_back_to_the_passages_it_saw(
    indexed: RagService, llm: FakeLLM
) -> None:
    llm.reply = "A mutex gives mutual exclusion."
    result = indexed.ask(QUESTION)
    assert result.answered
    assert not result.cited
    assert [c.number for c in result.citations] == list(range(1, len(result.context) + 1))


def test_model_saying_not_found_is_reported_as_unanswered(
    indexed: RagService, llm: FakeLLM
) -> None:
    llm.reply = NOT_FOUND
    result = indexed.ask(QUESTION)
    assert not result.answered
    assert result.answer.startswith("I couldn't find")
    assert result.citations == []
    assert result.context  # what the model saw stays available for debugging


def test_irrelevant_question_never_reaches_the_model(indexed: RagService, llm: FakeLLM) -> None:
    result = indexed.ask("zebra giraffe safari")
    assert not result.answered
    assert result.answer.startswith("I couldn't find")
    assert llm.calls == []


def test_french_question_gets_a_french_refusal(indexed: RagService, llm: FakeLLM) -> None:
    result = indexed.ask("Quelle est la différence entre un zebra et une girafe ?")
    assert result.answer.startswith("Je n'ai pas trouvé")
    assert llm.calls == []


def test_empty_index_never_reaches_the_model(service: RagService, llm: FakeLLM) -> None:
    result = service.ask(QUESTION)
    assert not result.answered
    assert "index is empty" in result.answer
    assert llm.calls == []


def test_blank_question_is_rejected(indexed: RagService) -> None:
    with pytest.raises(ValueError, match="empty"):
        indexed.ask("   ")


def test_source_filter_limits_the_passages(indexed: RagService, llm: FakeLLM) -> None:
    result = indexed.ask("critical section mutex address", sources=["os.txt"])
    assert {r.chunk.source for r in result.context} == {"os.txt"}


def test_top_k_limits_the_passages(indexed: RagService) -> None:
    assert len(indexed.ask("mutex critical section subnet mask", top_k=1).context) == 1


def test_bm25_mode_works_without_the_cosine_gate(indexed: RagService, llm: FakeLLM) -> None:
    result = indexed.ask("mutex", mode="bm25")
    assert result.answered
    assert result.context[0].chunk.source == "os.txt"
    assert not indexed.ask("zebra", mode="bm25").answered


def test_model_errors_are_not_swallowed(indexed: RagService, llm: FakeLLM) -> None:
    llm.error = OllamaUnavailableError("Cannot reach Ollama")
    with pytest.raises(OllamaUnavailableError):
        indexed.ask(QUESTION)


def test_relevance_threshold_comes_from_settings(settings: Settings, llm: FakeLLM) -> None:
    strict = Settings(
        data_dir=settings.data_dir,
        chroma_dir=settings.chroma_dir,
        embedding_model="hashing",
        min_relevance=0.99,
    )
    service = RagService(strict, embedder=HashingEmbedder(), llm=llm)
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "os.txt").write_text(MUTEX)
    list(service.ingest_directory(settings.data_dir))
    assert not service.ask(QUESTION).answered
    assert llm.calls == []


# ---- API --------------------------------------------------------------------


@pytest.fixture
def client(indexed: RagService) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: indexed
    yield TestClient(app)


def test_ask_endpoint_returns_answer_and_numbered_sources(client: TestClient) -> None:
    r = client.post("/ask", json={"question": QUESTION})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "A mutex gives mutual exclusion [1]."
    assert body["answered"] is True
    assert body["cited"] is True
    assert body["sources"] == [
        {
            "number": 1,
            "source": "os.txt",
            "page": 1,
            "snippet": MUTEX,
            "score": pytest.approx(body["sources"][0]["score"]),
        }
    ]
    assert 0.0 < body["sources"][0]["score"] <= 1.0


def test_ask_endpoint_reports_unanswered_questions(client: TestClient) -> None:
    body = client.post("/ask", json={"question": "zebra giraffe safari"}).json()
    assert body["answered"] is False
    assert body["sources"] == []


def test_ask_endpoint_accepts_a_source_filter_and_mode(client: TestClient) -> None:
    r = client.post(
        "/ask", json={"question": "mutex", "sources": ["os.txt"], "mode": "bm25", "top_k": 2}
    )
    assert r.status_code == 200
    assert r.json()["answered"] is True


def test_ask_endpoint_rejects_bad_input(client: TestClient) -> None:
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "mutex", "mode": "semantic"}).status_code == 422


def test_ask_endpoint_returns_503_when_ollama_is_down(
    client: TestClient, llm: FakeLLM
) -> None:
    llm.error = OllamaUnavailableError("Cannot reach Ollama at http://localhost:11434.")
    r = client.post("/ask", json={"question": QUESTION})
    assert r.status_code == 503
    assert "Cannot reach Ollama" in r.json()["detail"]


# ---- CLI --------------------------------------------------------------------


@pytest.fixture
def cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, llm: FakeLLM
) -> FakeLLM:
    data = tmp_path / "cli-data"
    data.mkdir()
    (data / "os.txt").write_text(MUTEX)
    monkeypatch.setenv("VECTORNOTE_DATA_DIR", str(data))
    monkeypatch.setenv("VECTORNOTE_CHROMA_DIR", str(tmp_path / "cli-db"))
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "hashing")
    monkeypatch.setattr("vectornote.service.OllamaClient", lambda url, model: llm)
    assert main(["ingest"]) == 0
    return llm


def test_cli_ask_prints_the_answer_and_its_sources(
    cli: FakeLLM, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert main(["ask", QUESTION]) == 0
    out = capsys.readouterr().out
    assert "A mutex gives mutual exclusion [1]." in out
    assert "Sources:" in out
    assert "[1] os.txt, p. 1" in out


def test_cli_ask_labels_uncited_answers(cli: FakeLLM, capsys: pytest.CaptureFixture[str]) -> None:
    cli.reply = "A mutex gives mutual exclusion."
    capsys.readouterr()
    assert main(["ask", QUESTION]) == 0
    assert "Related passages" in capsys.readouterr().out


def test_cli_ask_unanswered_question(cli: FakeLLM, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["ask", "zebra giraffe safari"]) == 0
    out = capsys.readouterr().out
    assert "couldn't find" in out
    assert "Sources" not in out
    assert cli.calls == []


def test_cli_ask_unknown_source(cli: FakeLLM, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ask", QUESTION, "--source", "missing.pdf"]) == 2
    assert "not indexed" in capsys.readouterr().err


def test_cli_ask_reports_ollama_problems(cli: FakeLLM, capsys: pytest.CaptureFixture[str]) -> None:
    cli.error = OllamaUnavailableError("Cannot reach Ollama at http://localhost:11434.")
    capsys.readouterr()
    assert main(["ask", QUESTION]) == 2
    assert "Cannot reach Ollama" in capsys.readouterr().err
