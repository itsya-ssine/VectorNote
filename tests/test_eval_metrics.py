from __future__ import annotations

import json
from pathlib import Path

import pytest

from vectornote.evaluation.metrics import (
    AnswerRecord,
    AnswerSummary,
    GateRow,
    RetrievalRecord,
    RetrievalSummary,
    citations_hit,
    first_hit_rank,
    gate_table,
    hit_cutoffs,
    keyword_coverage,
    mean,
    percentile,
    summarize_answers,
    summarize_retrieval,
)
from vectornote.evaluation.dataset import Evidence
from vectornote.evaluation.report import (
    RunInfo,
    build_payload,
    format_markdown,
    format_text,
    write_json,
)
from vectornote.models import Chunk, Citation, SearchResult


def _result(source: str, page: int, index: int = 0) -> SearchResult:
    chunk = Chunk(chunk_id=f"{source}#{page}-{index}", text="text", source=source, page=page)
    return SearchResult(chunk=chunk, score=1.0)


def _citation(source: str, page: int) -> Citation:
    return Citation(number=1, source=source, page=page, snippet="s", score=0.5)


def _record(
    id: str, answerable: bool = True, rank: int | None = None, cosine: float | None = None,
    latency: float = 10.0,
) -> RetrievalRecord:
    return RetrievalRecord(id, answerable, rank, cosine, latency)


def _answer(
    id: str,
    answerable: bool = True,
    answered: bool = True,
    cited: bool = True,
    correct: bool | None = None,
    coverage: float | None = None,
    faithful: bool | None = None,
    latency: float = 2.0,
) -> AnswerRecord:
    return AnswerRecord(
        id=id, answerable=answerable, answered=answered, cited=cited, citation_correct=correct,
        keyword_coverage=coverage, faithful=faithful, latency_s=latency,
        standalone_question="q", answer="a", cited_pages=[], context_pages=[],
    )


EVIDENCE = [Evidence(source="os.pdf", page=3), Evidence(source="os.pdf", page=4)]


# ---- helpers ---------------------------------------------------------------


def test_first_hit_rank_is_one_based_and_accepts_any_expected_page() -> None:
    results = [_result("net.pdf", 1), _result("os.pdf", 4), _result("os.pdf", 3)]
    assert first_hit_rank(results, EVIDENCE) == 2
    assert first_hit_rank(results[:1], EVIDENCE) is None
    assert first_hit_rank([], EVIDENCE) is None


def test_first_hit_rank_matches_file_and_page_together() -> None:
    assert first_hit_rank([_result("net.pdf", 3)], EVIDENCE) is None


def test_hit_cutoffs_include_k_and_never_exceed_it() -> None:
    assert hit_cutoffs(5) == (1, 3, 5)
    assert hit_cutoffs(1) == (1,)
    assert hit_cutoffs(4) == (1, 3, 4)
    assert hit_cutoffs(20) == (1, 3, 5, 10, 20)


def test_citations_hit_needs_an_expected_page() -> None:
    assert citations_hit([_citation("net.pdf", 1), _citation("os.pdf", 3)], EVIDENCE)
    assert not citations_hit([_citation("net.pdf", 3)], EVIDENCE)
    assert not citations_hit([], EVIDENCE)


def test_keyword_coverage_ignores_case_and_handles_no_keywords() -> None:
    assert keyword_coverage("FIFO suffers from Belady's anomaly", ["fifo", "Belady"]) == 1.0
    assert keyword_coverage("FIFO is simple", ["fifo", "Belady"]) == 0.5
    assert keyword_coverage("anything", []) is None


def test_mean_and_percentile() -> None:
    assert mean([]) is None
    assert mean([1.0, 2.0, 6.0]) == 3.0
    assert percentile([], 0.5) is None
    assert percentile([7.0], 0.95) == 7.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert percentile([4.0, 1.0, 3.0, 2.0], 1.0) == 4.0
    assert percentile([10.0, 20.0], 0.95) == pytest.approx(19.5)


# ---- retrieval summary -----------------------------------------------------


def test_retrieval_summary_hit_rate_and_mrr() -> None:
    records = [
        _record("a", rank=1),
        _record("b", rank=2),
        _record("c", rank=5),
        _record("d", rank=None),
        _record("u", answerable=False),
    ]
    summary = summarize_retrieval("hybrid", 5, records, skipped=2)
    assert (summary.answerable, summary.unanswerable, summary.skipped) == (4, 1, 2)
    assert summary.hit_rate == {1: 0.25, 3: 0.5, 5: 0.75}
    assert summary.mrr == pytest.approx((1 + 0.5 + 0.2 + 0) / 4)
    assert summary.misses == ["d"]
    assert summary.gate == []  # no thresholds were requested


def test_retrieval_summary_latency_covers_every_question() -> None:
    records = [_record("a", rank=1, latency=10.0), _record("u", False, latency=30.0)]
    summary = summarize_retrieval("vector", 5, records)
    assert summary.latency_mean_ms == 20.0
    assert summary.latency_p50_ms == 20.0


def test_retrieval_summary_without_answerable_questions() -> None:
    summary = summarize_retrieval("vector", 5, [_record("u", False)])
    assert summary.hit_rate == {}
    assert summary.mrr is None


def test_gate_table_shows_the_trade_off_of_each_threshold() -> None:
    records = [
        _record("a", rank=1, cosine=0.60),
        _record("b", rank=1, cosine=0.30),
        _record("u1", False, cosine=0.20),
        _record("u2", False, cosine=0.30),
        _record("u3", False, cosine=None),  # nothing was found at all
    ]
    rows = gate_table(records, [0.35, 0.25, 0.25])
    assert [row.threshold for row in rows] == [0.25, 0.35]  # sorted, no duplicates
    low, high = rows
    assert low.answerable_kept == 1.0
    assert low.unanswerable_refused == pytest.approx(2 / 3)  # u2 still gets through
    assert high.answerable_kept == 0.5  # b is now lost
    assert high.unanswerable_refused == 1.0


def test_gate_table_has_no_rate_for_an_empty_group() -> None:
    rows = gate_table([_record("a", rank=1, cosine=0.5)], [0.3])
    assert rows == [GateRow(0.3, 1.0, None)]


# ---- answer summary --------------------------------------------------------


def test_answer_summary_rates() -> None:
    records = [
        _answer("a", correct=True, coverage=1.0, faithful=True),
        _answer("b", correct=False, coverage=0.5, faithful=False, cited=False),
        _answer("c", answered=False),  # false refusal
        _answer("u1", answerable=False, answered=False),  # correct refusal
        _answer("u2", answerable=False, answered=True),  # made something up
    ]
    summary = summarize_answers(records, "hybrid", "llama3.2:3b")
    assert (summary.answerable, summary.unanswerable) == (3, 2)
    assert summary.answer_rate == pytest.approx(2 / 3)
    assert summary.refusal_rate == 0.5
    assert summary.cited_rate == 0.5
    assert summary.citation_correct_rate == 0.5
    assert summary.keyword_coverage == 0.75
    assert summary.faithfulness == 0.5
    assert summary.judged == 2
    assert summary.false_refusals == ["c"]
    assert summary.unwanted_answers == ["u2"]
    assert summary.latency_p50_s == 2.0


def test_answer_summary_faithfulness_is_none_without_a_judge() -> None:
    summary = summarize_answers([_answer("a", correct=True)], "hybrid", "m")
    assert summary.faithfulness is None
    assert summary.judged == 0
    assert summary.keyword_coverage is None


def test_answer_summary_of_nothing_is_all_none() -> None:
    summary = summarize_answers([], "hybrid", "m")
    assert summary.answer_rate is None
    assert summary.refusal_rate is None
    assert summary.latency_p50_s is None


# ---- report ----------------------------------------------------------------


INFO = RunInfo(
    questions_file="eval/questions.jsonl", questions=5, embedding_model="hashing",
    llm_model="llama3.2:3b", chunk_size=800, chunk_overlap=100, min_relevance=0.25, top_k=5,
)


def _summaries() -> tuple[list[RetrievalSummary], AnswerSummary]:
    records = [_record("a", rank=1, cosine=0.6), _record("b", rank=None, cosine=0.3),
               _record("u", False, cosine=0.1)]
    retrievals = [
        summarize_retrieval("vector", 5, records, skipped=1, gate_thresholds=[0.25]),
        summarize_retrieval("bm25", 5, records),
    ]
    answers = summarize_answers(
        [_answer("a", correct=True, coverage=1.0), _answer("u", False, answered=False)],
        "hybrid", "llama3.2:3b",
    )
    return retrievals, answers


def test_text_report_lists_every_mode_and_the_threshold_table() -> None:
    retrievals, answers = _summaries()
    text = format_text(INFO, retrievals, answers)
    assert "Retrieval, top 5 (2 answerable, 1 unanswerable; 1 follow-up(s) skipped" in text
    assert "hit@1" in text and "hit@3" in text and "hit@5" in text
    assert "vector" in text and "bm25" in text
    assert "missed in vector: b" in text
    assert "0.25 (current)" in text  # only the vector summary has a gate table
    assert "Answers (hybrid search, model llama3.2:3b)" in text
    assert "answered but should not have: none" in text


def test_text_report_without_answers_stops_after_retrieval() -> None:
    retrievals, _ = _summaries()
    assert "Answers" not in format_text(INFO, retrievals)


def test_markdown_report_uses_tables_and_states_its_settings() -> None:
    retrievals, answers = _summaries()
    md = format_markdown(INFO, retrievals, answers)
    assert md.startswith("Measured on 5 questions with `hashing`, chunks of 800 characters")
    assert "| mode | hit@1 | hit@3 | hit@5 | MRR | p50 ms | p95 ms |" in md
    assert "|---|---|---|---|---|---|---|" in md
    assert "| metric | result |" in md
    assert "no verdicts" in md  # the judge did not run


def test_json_payload_round_trips(tmp_path: Path) -> None:
    retrievals, answers = _summaries()
    records = [_answer("a", correct=True)]
    payload = build_payload(INFO, retrievals, answers, records)
    target = tmp_path / "out" / "results.json"
    write_json(target, payload)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["info"]["embedding_model"] == "hashing"
    assert data["retrieval"][0]["mode"] == "vector"
    assert data["retrieval"][0]["hit_rate"] == {"1": 0.5, "3": 0.5, "5": 0.5}
    assert data["answer_records"][0]["id"] == "a"
    assert data["generated_at"].endswith("+00:00")
