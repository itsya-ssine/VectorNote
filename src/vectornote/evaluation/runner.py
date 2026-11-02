"""Run an evaluation question set against the index and collect the metrics.

Retrieval needs only the embedder and the index, so it runs offline and quickly. Answers
call the local model once per question (plus once more per question with the optional judge).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence

from vectornote.evaluation.dataset import EvalQuestion
from vectornote.evaluation.judge import judge_faithfulness
from vectornote.evaluation.metrics import (
    GATE_THRESHOLDS,
    AnswerRecord,
    AnswerSummary,
    RetrievalRecord,
    RetrievalSummary,
    citations_hit,
    first_hit_rank,
    keyword_coverage,
    summarize_answers,
    summarize_retrieval,
)
from vectornote.service import RagService

Clock = Callable[[], float]
Progress = Callable[[int, int], None]

# Keyword-only search has no cosine scores, so there is no relevance threshold to tune.
_NO_COSINE = "bm25"


def resolve_queries(
    service: RagService, questions: Sequence[EvalQuestion], rewrite: bool = False
) -> dict[str, str]:
    """Map each question id to the text to search for.

    Follow-up questions (those with a `history`) only make sense once rewritten into a
    standalone question, which needs the local model. Without `rewrite` they are left out,
    and the retrieval summary reports how many were skipped.
    """
    queries: dict[str, str] = {}
    for question in questions:
        if not question.history:
            queries[question.id] = question.question.strip()
        elif rewrite:
            queries[question.id] = service.standalone_question(
                question.question, question.history
            )
    return queries


def run_retrieval(
    service: RagService,
    questions: Sequence[EvalQuestion],
    queries: Mapping[str, str],
    mode: str,
    k: int,
    clock: Clock = time.perf_counter,
) -> RetrievalSummary:
    """Search for every question in one mode and score where the expected pages rank.

    Searches run without the relevance gate, so every result is visible; the gate table in
    the summary shows what each threshold would have done. A warm-up search runs first so
    the latency numbers do not include loading the embedding model or building the index.
    """
    runnable = [q for q in questions if q.id in queries]
    skipped = len(questions) - len(runnable)
    if runnable:
        service.search(queries[runnable[0].id], k, mode=mode)

    records: list[RetrievalRecord] = []
    for question in runnable:
        start = clock()
        results = service.search(queries[question.id], k, mode=mode)
        elapsed_ms = (clock() - start) * 1000
        cosines = [r.vector_score for r in results if r.vector_score is not None]
        records.append(
            RetrievalRecord(
                id=question.id,
                answerable=question.answerable,
                rank=first_hit_rank(results, question.expected) if question.answerable else None,
                best_cosine=max(cosines, default=None),
                latency_ms=elapsed_ms,
            )
        )
    thresholds = (
        None if mode == _NO_COSINE else {*GATE_THRESHOLDS, service.settings.min_relevance}
    )
    return summarize_retrieval(mode, k, records, skipped, thresholds)


def run_answers(
    service: RagService,
    questions: Sequence[EvalQuestion],
    mode: str | None,
    k: int,
    judge: bool = False,
    clock: Clock = time.perf_counter,
    progress: Progress | None = None,
) -> tuple[AnswerSummary, list[AnswerRecord]]:
    """Ask every question (follow-ups with their history) and score the answers.

    Latency is the time `ask` takes, including query rewriting. The judge, when enabled,
    runs afterwards on each answered question and is not part of the latency.
    Returns the summary and the per-question records (answers included, for manual review).
    """
    records: list[AnswerRecord] = []
    for number, question in enumerate(questions, start=1):
        start = clock()
        result = service.ask(
            question.question, top_k=k, mode=mode, history=question.history or None
        )
        elapsed = clock() - start

        counted = question.answerable and result.answered
        records.append(
            AnswerRecord(
                id=question.id,
                answerable=question.answerable,
                answered=result.answered,
                cited=result.cited,
                citation_correct=(
                    result.cited and citations_hit(result.citations, question.expected)
                    if counted
                    else None
                ),
                keyword_coverage=(
                    keyword_coverage(result.answer, question.keywords) if counted else None
                ),
                faithful=(
                    judge_faithfulness(service.llm, result.answer, result.context)
                    if judge and result.answered
                    else None
                ),
                latency_s=elapsed,
                standalone_question=result.standalone_question,
                answer=result.answer,
                cited_pages=(
                    [f"{c.source} p. {c.page}" for c in result.citations] if result.cited else []
                ),
                context_pages=[f"{c.chunk.source} p. {c.chunk.page}" for c in result.context],
            )
        )
        if progress is not None:
            progress(number, len(questions))
    summary = summarize_answers(
        records, mode or service.settings.retrieval_mode, service.settings.llm_model
    )
    return summary, records
