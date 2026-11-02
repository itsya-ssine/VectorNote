"""Present evaluation results: a terminal summary, README-ready Markdown, and a JSON record."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vectornote.evaluation.metrics import (
    AnswerRecord,
    AnswerSummary,
    RetrievalSummary,
)


@dataclass(frozen=True)
class RunInfo:
    """The settings a run used, so a results table can be reproduced."""

    questions_file: str
    questions: int
    embedding_model: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    min_relevance: float
    top_k: int


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{round(value * 100)}%"


def _fixed(value: float | None, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _ids(ids: Sequence[str]) -> str:
    return ", ".join(ids) if ids else "none"


def _gate_source(
    retrievals: Sequence[RetrievalSummary], preferred: str
) -> RetrievalSummary | None:
    """The summary whose relevance-threshold table to show (the configured mode if possible)."""
    with_gate = [r for r in retrievals if r.gate]
    for summary in with_gate:
        if summary.mode == preferred:
            return summary
    return with_gate[0] if with_gate else None


def _retrieval_note(summary: RetrievalSummary) -> str:
    note = f"{summary.answerable} answerable, {summary.unanswerable} unanswerable"
    if summary.skipped:
        note += f"; {summary.skipped} follow-up(s) skipped, use --rewrite to include them"
    return note


def _table(header: Sequence[str], rows: Sequence[Sequence[str]], markdown: bool) -> list[str]:
    """Rows as an aligned text table, or as a Markdown table."""
    if markdown:
        lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
        lines += ["| " + " | ".join(row) + " |" for row in rows]
        return lines
    widths = [max(len(str(cell)) for cell in column) for column in zip(header, *rows, strict=True)]
    return [
        "  ".join(str(cell).ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in (header, *rows)
    ]


def _retrieval_rows(retrievals: Sequence[RetrievalSummary]) -> tuple[list[str], list[list[str]]]:
    cutoffs = sorted(retrievals[0].hit_rate) if retrievals else []
    header = ["mode", *(f"hit@{c}" for c in cutoffs), "MRR", "p50 ms", "p95 ms"]
    rows = [
        [
            r.mode,
            *(_pct(r.hit_rate.get(c)) for c in cutoffs),
            _fixed(r.mrr, 2),
            _fixed(r.latency_p50_ms, 1),
            _fixed(r.latency_p95_ms, 1),
        ]
        for r in retrievals
    ]
    return header, rows


def _gate_rows(summary: RetrievalSummary, current: float) -> tuple[list[str], list[list[str]]]:
    header = ["threshold", "answerable kept", "unanswerable refused"]
    rows = [
        [
            f"{row.threshold:.2f}" + (" (current)" if abs(row.threshold - current) < 1e-9 else ""),
            _pct(row.answerable_kept),
            _pct(row.unanswerable_refused),
        ]
        for row in summary.gate
    ]
    return header, rows


def _answer_rows(summary: AnswerSummary) -> list[list[str]]:
    faithfulness = (
        f"{_pct(summary.faithfulness)} ({summary.judged} judged)"
        if summary.judged
        else "no verdicts (needs --judge)"
    )
    latency_p95 = _fixed(summary.latency_p95_s, 1)
    return [
        ["answered (of answerable)", _pct(summary.answer_rate)],
        ["refused correctly (of unanswerable)", _pct(summary.refusal_rate)],
        ["answers with citations", _pct(summary.cited_rate)],
        ["citation on an expected page", _pct(summary.citation_correct_rate)],
        ["keyword coverage", _pct(summary.keyword_coverage)],
        ["faithfulness (model judge)", faithfulness],
        ["latency p50 / p95", f"{_fixed(summary.latency_p50_s, 1)} s / {latency_p95} s"],
    ]


def format_text(
    info: RunInfo,
    retrievals: Sequence[RetrievalSummary],
    answers: AnswerSummary | None = None,
) -> str:
    """The summary printed in the terminal."""
    lines: list[str] = []
    if retrievals:
        first = retrievals[0]
        lines.append(f"Retrieval, top {first.k} ({_retrieval_note(first)})")
        header, rows = _retrieval_rows(retrievals)
        lines += ["  " + line for line in _table(header, rows, markdown=False)]
        for summary in retrievals:
            if summary.misses:
                lines.append(f"  missed in {summary.mode}: {_ids(summary.misses)}")
        source = _gate_source(retrievals, "hybrid")
        if source is not None:
            lines += ["", f"Relevance threshold ({source.mode}, minimum cosine similarity)"]
            header, rows = _gate_rows(source, info.min_relevance)
            lines += ["  " + line for line in _table(header, rows, markdown=False)]
    if answers is not None:
        lines += ["", f"Answers ({answers.mode} search, model {answers.model})"]
        rows = _answer_rows(answers)
        lines += ["  " + line for line in _table(["metric", "result"], rows, markdown=False)]
        lines.append(f"  answered but should not have: {_ids(answers.unwanted_answers)}")
        lines.append(f"  refused but should have answered: {_ids(answers.false_refusals)}")
    return "\n".join(lines)


def format_markdown(
    info: RunInfo,
    retrievals: Sequence[RetrievalSummary],
    answers: AnswerSummary | None = None,
) -> str:
    """The same results as Markdown tables, ready to paste into the README."""
    lines = [
        f"Measured on {info.questions} questions with `{info.embedding_model}`, "
        f"chunks of {info.chunk_size} characters ({info.chunk_overlap} overlap), top {info.top_k}.",
    ]
    if retrievals:
        lines += ["", "**Retrieval**", ""]
        header, rows = _retrieval_rows(retrievals)
        lines += _table(header, rows, markdown=True)
        lines += ["", _retrieval_note(retrievals[0]) + "."]
        source = _gate_source(retrievals, "hybrid")
        if source is not None:
            lines += ["", f"**Relevance threshold ({source.mode})**", ""]
            header, rows = _gate_rows(source, info.min_relevance)
            lines += _table(header, rows, markdown=True)
    if answers is not None:
        lines += ["", f"**Answers** ({answers.mode} search, `{answers.model}`)", ""]
        lines += _table(["metric", "result"], _answer_rows(answers), markdown=True)
    return "\n".join(lines)


def build_payload(
    info: RunInfo,
    retrievals: Sequence[RetrievalSummary],
    answers: AnswerSummary | None = None,
    records: Sequence[AnswerRecord] = (),
) -> dict[str, Any]:
    """Everything about a run as plain data: settings, summaries and every answer."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "info": asdict(info),
        "retrieval": [asdict(summary) for summary in retrievals],
        "answers": asdict(answers) if answers is not None else None,
        "answer_records": [asdict(record) for record in records],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
