"""The evaluation question set: file format, loading and consistency checks.

Each line of the JSONL file is one question with the pages that answer it, so that
retrieval can be scored (does the right page come back?) and answers can be judged.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vectornote.models import ChatTurn

QuestionType = Literal["factual", "definition", "comparison", "procedure", "unanswerable"]

RECOMMENDED_MIN = 30
RECOMMENDED_MAX = 50
MIN_UNANSWERABLE_SHARE = 0.1
MAX_SINGLE_SOURCE_SHARE = 0.5
# A run of this many identical words means the question was copied from the passage.
COPIED_RUN_WORDS = 6

_WORD = re.compile(r"\w+")


class Evidence(BaseModel):
    """A page that answers the question."""

    source: str
    page: int = Field(ge=1)


class EvalQuestion(BaseModel):
    """One evaluation question.

    `expected` lists every page that answers it (any one is a hit). Unanswerable
    questions, which test the "I couldn't find it" path, have no expected pages.
    `history` makes it a follow-up question. `keywords` are terms a correct answer
    should contain. `passage` and `needs_review` only exist in scaffolded drafts.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str
    type: QuestionType = "factual"
    language: Literal["en", "fr"] = "en"
    expected: list[Evidence] = Field(default_factory=list)
    reference_answer: str = ""
    keywords: list[str] = Field(default_factory=list)
    history: list[ChatTurn] = Field(default_factory=list)
    passage: str | None = None
    needs_review: bool = False

    @property
    def answerable(self) -> bool:
        return self.type != "unanswerable"


class DatasetError(ValueError):
    """The question file cannot be read."""


def load_questions(path: Path) -> list[EvalQuestion]:
    """Read a JSONL file (blank lines are ignored). Errors name the offending line."""
    questions: list[EvalQuestion] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            questions.append(EvalQuestion.model_validate(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{path}:{number}: not valid JSON ({exc.msg})") from exc
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'line'}: {err['msg']}"
                for err in exc.errors()
            )
            raise DatasetError(f"{path}:{number}: {problems}") from exc
    return questions


def write_questions(path: Path, questions: Iterable[EvalQuestion]) -> None:
    """Write questions as JSONL, with the useful fields always visible and empty extras left out."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for q in questions:
        data: dict[str, object] = {
            "id": q.id,
            "question": q.question,
            "type": q.type,
            "language": q.language,
            "expected": [e.model_dump() for e in q.expected],
            "reference_answer": q.reference_answer,
        }
        if q.keywords:
            data["keywords"] = q.keywords
        if q.history:
            data["history"] = [turn.model_dump() for turn in q.history]
        if q.passage is not None:
            data["passage"] = q.passage
        if q.needs_review:
            data["needs_review"] = True
        lines.append(json.dumps(data, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass
class CheckReport:
    """Problems found in a question set, plus a summary of what it contains."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total: int = 0
    answerable: int = 0
    unanswerable: int = 0
    follow_ups: int = 0
    by_type: Counter[str] = field(default_factory=Counter)
    by_language: Counter[str] = field(default_factory=Counter)
    by_source: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.errors


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _copied_run(question: str, passage: str) -> bool:
    q = _words(question)
    if len(q) < COPIED_RUN_WORDS:
        return False
    p = _words(passage)
    size = COPIED_RUN_WORDS
    grams = {tuple(p[i:i + size]) for i in range(len(p) - size + 1)}
    return any(tuple(q[i:i + size]) in grams for i in range(len(q) - size + 1))


def check_questions(
    questions: Sequence[EvalQuestion],
    pages: Mapping[str, set[int]],
    passages: Mapping[tuple[str, int], str] | None = None,
) -> CheckReport:
    """Check a question set against the index.

    `pages` maps each indexed file to the pages that have text. `passages` (optional)
    maps `(file, page)` to its text, to detect questions copied from the course material.
    """
    report = CheckReport(total=len(questions))
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()

    for q in questions:
        label = q.id
        if q.id in seen_ids:
            report.errors.append(f"{label}: duplicate id")
        seen_ids.add(q.id)

        text = q.question.strip()
        if not text or text.upper().startswith("TODO"):
            report.errors.append(f"{label}: the question is still a placeholder")
        elif text.lower() in seen_questions:
            report.warnings.append(f"{label}: same question text as an earlier entry")
        seen_questions.add(text.lower())

        if q.needs_review:
            report.errors.append(f"{label}: still marked needs_review (check it, then remove it)")
        if q.passage is not None:
            report.warnings.append(f"{label}: delete the `passage` field (it copies course text)")

        report.by_type[q.type] += 1
        report.by_language[q.language] += 1
        if q.history:
            report.follow_ups += 1

        if not q.answerable:
            report.unanswerable += 1
            if q.expected:
                report.errors.append(f"{label}: an unanswerable question has expected pages")
            continue

        report.answerable += 1
        if not q.expected:
            report.errors.append(f"{label}: no expected pages (or set type to unanswerable)")
        if not q.reference_answer.strip():
            report.errors.append(f"{label}: no reference_answer")
        if any(not k.strip() for k in q.keywords):
            report.errors.append(f"{label}: empty keyword")

        for evidence in q.expected:
            report.by_source[evidence.source] += 1
            if evidence.source not in pages:
                report.errors.append(f"{label}: '{evidence.source}' is not in the index")
            elif evidence.page not in pages[evidence.source]:
                known = sorted(pages[evidence.source])
                report.errors.append(
                    f"{label}: {evidence.source} has no indexed text on page {evidence.page} "
                    f"(pages with text: {known[0]}-{known[-1]})"
                )
            elif passages is not None and _copied_run(
                text, passages.get((evidence.source, evidence.page), "")
            ):
                report.warnings.append(
                    f"{label}: copies wording from {evidence.source} p. {evidence.page}; "
                    "ask it the way a student would, in your own words"
                )
                break

    _check_balance(report)
    return report


def _check_balance(report: CheckReport) -> None:
    if report.total < RECOMMENDED_MIN:
        report.warnings.append(
            f"only {report.total} questions; aim for {RECOMMENDED_MIN}-{RECOMMENDED_MAX} "
            "so the metrics are not dominated by a few questions"
        )
    elif report.total > RECOMMENDED_MAX * 2:
        report.warnings.append(f"{report.total} questions is a lot to maintain by hand")
    if report.total and report.unanswerable / report.total < MIN_UNANSWERABLE_SHARE:
        report.warnings.append(
            f"only {report.unanswerable} unanswerable question(s); add some (about 10-15%) "
            "so the relevance threshold can be tuned"
        )
    if report.answerable and report.by_source:
        source, count = report.by_source.most_common(1)[0]
        if count / report.answerable > MAX_SINGLE_SOURCE_SHARE and len(report.by_source) > 1:
            report.warnings.append(
                f"{source} supplies {count} of {report.answerable} answerable questions; "
                "spread them over more files"
            )
    if report.total >= RECOMMENDED_MIN and report.follow_ups == 0:
        report.warnings.append("no follow-up questions; add a few with `history` to test rewriting")
