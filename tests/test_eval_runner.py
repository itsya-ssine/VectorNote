from __future__ import annotations

from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from itertools import count
from pathlib import Path

import pytest

from tests.fakes import FakeLLM
from vectornote.config import Settings
from vectornote.embeddings.hashing import HashingEmbedder
from vectornote.evaluation.dataset import EvalQuestion, Evidence
from vectornote.evaluation.judge import JUDGE_SYSTEM_PROMPT
from vectornote.evaluation.runner import resolve_queries, run_answers, run_retrieval
from vectornote.models import ChatTurn
from vectornote.service import RagService

MUTEX = "A mutex gives mutual exclusion to a critical section. Only one thread holds it."
SUBNET = "A subnet mask separates the network part and the host part of an IP address."


def _question(
    id: str,
    text: str,
    source: str | None = None,
    type: str = "factual",
    keywords: list[str] | None = None,
    history: list[ChatTurn] | None = None,
) -> EvalQuestion:
    expected = [Evidence(source=source, page=1)] if source else []
    return EvalQuestion.model_validate(
        {
            "id": id,
            "question": text,
            "type": type,
            "expected": [e.model_dump() for e in expected],
            "reference_answer": "x" if expected else "",
            "keywords": keywords or [],
            "history": [turn.model_dump() for turn in (history or [])],
        }
    )


MUTEX_Q = _question(
    "q1", "How does a mutex protect a critical section?", "os.txt", keywords=["mutual"]
)
SUBNET_Q = _question("q2", "What does a subnet mask separate?", "net.txt", keywords=["host"])
LOST_Q = _question("q3", "Which thread holds the mutex?", "net.txt")  # wrong file on purpose
NONE_Q = _question("u1", "zebra giraffe safari", type="unanswerable")


class ScriptedLLM(FakeLLM):
    """Answers with `reply`, and answers the judge with `verdict`."""

    def __init__(self, reply: str, verdict: str = "SUPPORTED") -> None:
        super().__init__(reply)
        self.verdict = verdict
        self.judged = 0

    def complete(
        self, messages: Sequence[Mapping[str, str]], max_tokens: int | None = None
    ) -> str:
        if messages[0]["content"] == JUDGE_SYSTEM_PROMPT:
            self.judged += 1
            return self.verdict
        return super().complete(messages, max_tokens)

    def stream(self, messages: Sequence[Mapping[str, str]]) -> Generator[str, None, None]:
        yield from super().stream(messages)


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM("A mutex gives mutual exclusion to a critical section [1].")


@pytest.fixture
def service(tmp_path: Path, llm: ScriptedLLM) -> RagService:
    # The hashing embedder scores far lower than a real model, so the gate is pinned here
    # instead of following the production default.
    settings = Settings(
        data_dir=tmp_path / "data",
        chroma_dir=tmp_path / "db",
        embedding_model="hashing",
        min_relevance=0.25,
    )
    settings.data_dir.mkdir()
    (settings.data_dir / "os.txt").write_text(MUTEX)
    (settings.data_dir / "net.txt").write_text(SUBNET)
    svc = RagService(settings, embedder=HashingEmbedder(), llm=llm)
    list(svc.ingest_directory(settings.data_dir))
    return svc


def _clock(step: float = 1.0) -> Callable[[], float]:
    """A clock that advances by `step` seconds on every reading."""
    ticks: Iterator[int] = count()
    return lambda: next(ticks) * step


# ---- queries ---------------------------------------------------------------


def test_follow_ups_are_skipped_unless_they_are_rewritten(
    service: RagService, llm: ScriptedLLM
) -> None:
    history = [
        ChatTurn(role="user", content="What is a mutex?"),
        ChatTurn(role="assistant", content="A lock [1]."),
    ]
    follow_up = _question("f1", "How does it work?", "os.txt", history=history)
    questions = [MUTEX_Q, follow_up]

    assert resolve_queries(service, questions) == {"q1": MUTEX_Q.question}
    assert llm.rewrite_calls == []  # no model call without --rewrite

    llm.rewrite_reply = "How does a mutex work?"
    assert resolve_queries(service, questions, rewrite=True) == {
        "q1": MUTEX_Q.question,
        "f1": "How does a mutex work?",
    }
    assert len(llm.rewrite_calls) == 1


# ---- retrieval -------------------------------------------------------------


def test_retrieval_finds_the_expected_pages(service: RagService) -> None:
    questions = [MUTEX_Q, SUBNET_Q, LOST_Q, NONE_Q]
    queries = resolve_queries(service, questions)
    summary = run_retrieval(service, questions, queries, "hybrid", k=3, clock=_clock(0.001))
    assert (summary.answerable, summary.unanswerable, summary.skipped) == (3, 1, 0)
    assert summary.hit_rate[3] == pytest.approx(1.0)  # only two files: always inside the top 3
    assert summary.hit_rate[1] == pytest.approx(2 / 3)  # LOST_Q expects the wrong file first
    assert summary.misses == []
    assert 0 < summary.mrr <= 1  # type: ignore[operator]


def test_retrieval_reports_skipped_questions_and_exact_latency(service: RagService) -> None:
    history = [ChatTurn(role="user", content="hi"), ChatTurn(role="assistant", content="hello")]
    follow_up = _question("f1", "and then?", "os.txt", history=history)
    questions = [MUTEX_Q, SUBNET_Q, follow_up]
    queries = resolve_queries(service, questions)
    summary = run_retrieval(service, questions, queries, "vector", k=5, clock=_clock(0.5))
    assert summary.skipped == 1
    assert summary.answerable == 2
    # the clock moves 0.5 s per reading and each search reads it twice
    assert summary.latency_p50_ms == pytest.approx(500.0)
    assert summary.latency_p95_ms == pytest.approx(500.0)


def test_retrieval_gate_table_exists_only_for_modes_with_cosine_scores(
    service: RagService,
) -> None:
    questions = [MUTEX_Q, NONE_Q]
    queries = resolve_queries(service, questions)
    vector = run_retrieval(service, questions, queries, "vector", k=3)
    hybrid = run_retrieval(service, questions, queries, "hybrid", k=3)
    bm25 = run_retrieval(service, questions, queries, "bm25", k=3)
    assert 0.25 in [row.threshold for row in vector.gate]  # the configured threshold
    assert hybrid.gate
    assert bm25.gate == []
    row = {r.threshold: r for r in vector.gate}[0.25]
    assert row.answerable_kept == 1.0
    assert row.unanswerable_refused == 1.0  # the zebra question is below the gate


def test_retrieval_with_no_runnable_question_does_not_search(service: RagService) -> None:
    history = [ChatTurn(role="user", content="hi"), ChatTurn(role="assistant", content="hello")]
    only_follow_up = _question("f1", "and then?", "os.txt", history=history)
    summary = run_retrieval(service, [only_follow_up], {}, "hybrid", k=5)
    assert summary.skipped == 1
    assert summary.hit_rate == {}
    assert summary.latency_p50_ms is None


# ---- answers ---------------------------------------------------------------


def test_answers_are_scored_for_citations_keywords_and_refusals(
    service: RagService, llm: ScriptedLLM
) -> None:
    questions = [MUTEX_Q, SUBNET_Q, NONE_Q]
    summary, records = run_answers(service, questions, mode=None, k=3, clock=_clock(2.0))
    by_id = {r.id: r for r in records}

    mutex = by_id["q1"]
    assert mutex.answered and mutex.cited
    assert mutex.citation_correct is True
    assert mutex.keyword_coverage == 1.0
    assert mutex.cited_pages == ["os.txt p. 1"]
    assert "os.txt p. 1" in mutex.context_pages

    # the fixed reply cites passage [1], which for the subnet question is the wrong page
    subnet = by_id["q2"]
    assert subnet.answered
    assert subnet.keyword_coverage == 0.0

    zebra = by_id["u1"]
    assert not zebra.answered
    assert zebra.citation_correct is None and zebra.keyword_coverage is None
    assert zebra.cited_pages == [] and zebra.context_pages == []

    assert summary.refusal_rate == 1.0
    assert summary.unwanted_answers == []
    assert summary.mode == "hybrid" and summary.model == service.settings.llm_model
    assert summary.latency_p50_s == pytest.approx(2.0)
    assert llm.judged == 0  # the judge only runs when asked


def test_an_answer_without_citation_markers_is_not_a_correct_citation(
    service: RagService, llm: ScriptedLLM
) -> None:
    llm.reply = "A mutex gives mutual exclusion."
    _, [record] = run_answers(service, [MUTEX_Q], mode="vector", k=3)
    assert record.answered and not record.cited
    assert record.citation_correct is False
    assert record.cited_pages == []  # the fallback passages are not claimed as citations
    assert "os.txt p. 1" in record.context_pages


def test_refusals_are_counted_as_false_refusals_and_unwanted_answers(
    service: RagService, llm: ScriptedLLM
) -> None:
    llm.reply = "NOT_FOUND"
    summary, _ = run_answers(service, [MUTEX_Q, NONE_Q], mode=None, k=3)
    assert summary.answer_rate == 0.0
    assert summary.false_refusals == ["q1"]
    assert summary.refusal_rate == 1.0


def test_judge_runs_on_answered_questions_only(service: RagService, llm: ScriptedLLM) -> None:
    llm.verdict = "UNSUPPORTED"
    summary, records = run_answers(service, [MUTEX_Q, NONE_Q], mode=None, k=3, judge=True)
    assert llm.judged == 1  # the refused question has nothing to judge
    assert [r.faithful for r in records] == [False, None]
    assert summary.faithfulness == 0.0
    assert summary.judged == 1


def test_follow_up_questions_are_answered_with_their_history(
    service: RagService, llm: ScriptedLLM
) -> None:
    llm.rewrite_reply = "How does a mutex protect a critical section?"
    history = [
        ChatTurn(role="user", content="What is a mutex?"),
        ChatTurn(role="assistant", content="A lock [1]."),
    ]
    follow_up = _question("f1", "How does it protect things?", "os.txt", history=history)
    _, [record] = run_answers(service, [follow_up], mode=None, k=3)
    assert record.standalone_question == "How does a mutex protect a critical section?"
    assert record.citation_correct is True


def test_progress_is_reported_after_each_question(service: RagService) -> None:
    seen: list[tuple[int, int]] = []
    run_answers(
        service, [MUTEX_Q, NONE_Q], mode=None, k=3, progress=lambda d, n: seen.append((d, n))
    )
    assert seen == [(1, 2), (2, 2)]
