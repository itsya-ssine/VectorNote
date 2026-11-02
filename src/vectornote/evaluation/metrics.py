"""Metrics for the evaluation harness.

Everything here is plain arithmetic on already-collected results, so it needs no model,
index or network. The runner (`runner.py`) collects the per-question records, and the
`summarize_*` functions turn them into the numbers that go into the README.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from vectornote.evaluation.dataset import Evidence
from vectornote.models import Citation, SearchResult

# Hit rate is reported at these cutoffs (those not larger than k, plus k itself).
HIT_CUTOFFS = (1, 3, 5, 10)
# Cosine thresholds tried when tuning VECTORNOTE_MIN_RELEVANCE (the configured one is added).
GATE_THRESHOLDS = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50)

Page = tuple[str, int]


def page_set(evidence: Iterable[Evidence]) -> set[Page]:
    """The `(file, page)` pairs a question can be answered from."""
    return {(e.source, e.page) for e in evidence}


def first_hit_rank(results: Sequence[SearchResult], expected: Iterable[Evidence]) -> int | None:
    """1-based rank of the first result on an expected page, or None if there is none.

    Ranks count chunks, not pages: two chunks of the same page take two ranks.
    """
    wanted = page_set(expected)
    for rank, result in enumerate(results, start=1):
        if (result.chunk.source, result.chunk.page) in wanted:
            return rank
    return None


def hit_cutoffs(k: int) -> tuple[int, ...]:
    """The cutoffs hit rate is reported at for a search depth of `k`."""
    return tuple(sorted({c for c in HIT_CUTOFFS if c <= k} | {k}))


def citations_hit(citations: Iterable[Citation], expected: Iterable[Evidence]) -> bool:
    """True when at least one cited passage is on an expected page."""
    wanted = page_set(expected)
    return any((c.source, c.page) in wanted for c in citations)


def keyword_coverage(answer: str, keywords: Sequence[str]) -> float | None:
    """Share of `keywords` found in the answer (case-insensitive); None without keywords."""
    if not keywords:
        return None
    text = answer.casefold()
    found = sum(1 for keyword in keywords if keyword.casefold() in text)
    return found / len(keywords)


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(values: Sequence[float], q: float) -> float | None:
    """The `q`-quantile (0 to 1) with linear interpolation; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _share(count: int, total: int) -> float | None:
    return count / total if total else None


# ---- retrieval ------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalRecord:
    """What searching for one question produced.

    `best_cosine` is the highest cosine similarity among the results (None when the mode
    has no cosine scores or nothing was found). `rank` is only set for answerable questions.
    """

    id: str
    answerable: bool
    rank: int | None
    best_cosine: float | None
    latency_ms: float


@dataclass(frozen=True)
class GateRow:
    """What a relevance threshold would do: how many questions it keeps or refuses."""

    threshold: float
    answerable_kept: float | None
    unanswerable_refused: float | None


@dataclass(frozen=True)
class RetrievalSummary:
    """Retrieval quality and speed for one search mode."""

    mode: str
    k: int
    answerable: int
    unanswerable: int
    skipped: int
    hit_rate: dict[int, float]
    mrr: float | None
    latency_mean_ms: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    gate: list[GateRow] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)


def gate_table(
    records: Sequence[RetrievalRecord], thresholds: Iterable[float]
) -> list[GateRow]:
    """For each threshold: answerable questions that keep a passage, unanswerable ones refused.

    A question is kept when its best cosine similarity reaches the threshold. This is how
    `ask` decides whether to call the model, so it shows the trade-off of the setting.
    """
    answerable = [r for r in records if r.answerable]
    unanswerable = [r for r in records if not r.answerable]
    rows: list[GateRow] = []
    for threshold in sorted(set(thresholds)):
        kept = sum(
            1 for r in answerable if r.best_cosine is not None and r.best_cosine >= threshold
        )
        refused = sum(
            1 for r in unanswerable if r.best_cosine is None or r.best_cosine < threshold
        )
        rows.append(
            GateRow(threshold, _share(kept, len(answerable)), _share(refused, len(unanswerable)))
        )
    return rows


def summarize_retrieval(
    mode: str,
    k: int,
    records: Sequence[RetrievalRecord],
    skipped: int = 0,
    gate_thresholds: Iterable[float] | None = None,
) -> RetrievalSummary:
    """Hit rate at each cutoff, MRR and latency over the answerable questions.

    Pass `gate_thresholds` for modes that have cosine scores (vector and hybrid) to also
    get the relevance-threshold table.
    """
    answerable = [r for r in records if r.answerable]
    hit_rate: dict[int, float] = {}
    if answerable:
        for cutoff in hit_cutoffs(k):
            hits = sum(1 for r in answerable if r.rank is not None and r.rank <= cutoff)
            hit_rate[cutoff] = hits / len(answerable)
    reciprocal = [1 / r.rank if r.rank else 0.0 for r in answerable]
    latencies = [r.latency_ms for r in records]
    return RetrievalSummary(
        mode=mode,
        k=k,
        answerable=len(answerable),
        unanswerable=len(records) - len(answerable),
        skipped=skipped,
        hit_rate=hit_rate,
        mrr=mean(reciprocal),
        latency_mean_ms=mean(latencies),
        latency_p50_ms=percentile(latencies, 0.5),
        latency_p95_ms=percentile(latencies, 0.95),
        gate=gate_table(records, gate_thresholds) if gate_thresholds is not None else [],
        misses=[r.id for r in answerable if r.rank is None],
    )


# ---- answers --------------------------------------------------------------


@dataclass(frozen=True)
class AnswerRecord:
    """What asking one question produced.

    `citation_correct` is only set for answered, answerable questions: True when the answer
    cites a passage from an expected page (an answer without `[n]` markers is not correct).
    `faithful` is only set when the judge ran and gave a clear verdict. `cited_pages` lists
    the pages the answer cites (empty without markers), `context_pages` every page the
    model was given.
    """

    id: str
    answerable: bool
    answered: bool
    cited: bool
    citation_correct: bool | None
    keyword_coverage: float | None
    faithful: bool | None
    latency_s: float
    standalone_question: str
    answer: str
    cited_pages: list[str]
    context_pages: list[str]


@dataclass(frozen=True)
class AnswerSummary:
    """Answer quality over a whole question set."""

    mode: str
    model: str
    answerable: int
    unanswerable: int
    answer_rate: float | None
    refusal_rate: float | None
    cited_rate: float | None
    citation_correct_rate: float | None
    keyword_coverage: float | None
    faithfulness: float | None
    judged: int
    latency_mean_s: float | None
    latency_p50_s: float | None
    latency_p95_s: float | None
    false_refusals: list[str] = field(default_factory=list)
    unwanted_answers: list[str] = field(default_factory=list)


def summarize_answers(records: Sequence[AnswerRecord], mode: str, model: str) -> AnswerSummary:
    """Answer, refusal, citation, keyword and faithfulness rates plus latency.

    Rates over answerable questions: `answer_rate` (the model did not refuse),
    `cited_rate` and `citation_correct_rate` (of the answered ones). `refusal_rate` is over
    unanswerable questions: how often the system correctly said it could not find it.
    """
    answerable = [r for r in records if r.answerable]
    unanswerable = [r for r in records if not r.answerable]
    answered = [r for r in answerable if r.answered]
    refused = [r for r in unanswerable if not r.answered]
    judged = [r for r in answered if r.faithful is not None]
    coverage = [r.keyword_coverage for r in answered if r.keyword_coverage is not None]
    latencies = [r.latency_s for r in records]
    return AnswerSummary(
        mode=mode,
        model=model,
        answerable=len(answerable),
        unanswerable=len(unanswerable),
        answer_rate=_share(len(answered), len(answerable)),
        refusal_rate=_share(len(refused), len(unanswerable)),
        cited_rate=_share(sum(1 for r in answered if r.cited), len(answered)),
        citation_correct_rate=_share(
            sum(1 for r in answered if r.citation_correct), len(answered)
        ),
        keyword_coverage=mean(coverage),
        faithfulness=_share(sum(1 for r in judged if r.faithful), len(judged)),
        judged=len(judged),
        latency_mean_s=mean(latencies),
        latency_p50_s=percentile(latencies, 0.5),
        latency_p95_s=percentile(latencies, 0.95),
        false_refusals=[r.id for r in answerable if not r.answered],
        unwanted_answers=[r.id for r in unanswerable if r.answered],
    )
