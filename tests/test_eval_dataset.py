from __future__ import annotations

import json
from pathlib import Path

import pytest

from vectornote.evaluation import EvalQuestion, Evidence, check_questions, load_questions
from vectornote.evaluation import write_questions
from vectornote.evaluation.dataset import DatasetError
from vectornote.models import ChatTurn

PAGES = {"os.pdf": {1, 2, 3, 4}, "net.md": {1}}
PASSAGES = {
    ("os.pdf", 2): (
        "A mutex guarantees that only one thread at a time can enter the critical section."
    ),
}


def _q(id: str = "q1", **overrides: object) -> EvalQuestion:
    data: dict[str, object] = {
        "id": id,
        "question": "What does a mutex guarantee?",
        "type": "definition",
        "expected": [Evidence(source="os.pdf", page=2)],
        "reference_answer": "Only one thread at a time in the critical section.",
    }
    data.update(overrides)
    return EvalQuestion.model_validate(data)


def _many(count: int, **overrides: object) -> list[EvalQuestion]:
    return [_q(f"q{i}", question=f"Question number {i}?", **overrides) for i in range(count)]


# ---- file format --------------------------------------------------------------


def test_round_trip_keeps_everything(tmp_path: Path) -> None:
    original = [
        _q("q1", keywords=["mutex"], language="fr"),
        _q(
            "q2",
            question="and the second one?",
            history=[ChatTurn(role="user", content="hi"), ChatTurn(role="assistant", content="yo")],
        ),
        EvalQuestion(id="q3", question="Capital of Australia?", type="unanswerable"),
    ]
    path = tmp_path / "eval" / "questions.jsonl"
    write_questions(path, original)
    assert load_questions(path) == original
    first = json.loads(path.read_text().splitlines()[0])
    assert list(first)[:2] == ["id", "question"]  # readable field order


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    line = json.dumps({"id": "q1", "question": "x?", "type": "unanswerable"})
    path.write_text(f"\n{line}\n\n   \n{line.replace('q1', 'q2')}\n")
    assert [q.id for q in load_questions(path)] == ["q1", "q2"]


def test_errors_name_the_line(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text('{"id": "q1", "question": "ok?", "type": "unanswerable"}\n{not json}\n')
    with pytest.raises(DatasetError, match=r"q.jsonl:2: not valid JSON"):
        load_questions(path)

    path.write_text('{"id": "q1", "question": "x?", "type": "essay"}\n')
    with pytest.raises(DatasetError, match=r"q.jsonl:1: type"):
        load_questions(path)


def test_misspelled_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text('{"id": "q1", "question": "x?", "referance_answer": "typo"}\n')
    with pytest.raises(DatasetError, match="referance_answer"):
        load_questions(path)


def test_a_page_number_must_be_positive(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text('{"id": "q1", "question": "x?", "expected": [{"source": "a", "page": 0}]}\n')
    with pytest.raises(DatasetError, match="page"):
        load_questions(path)


# ---- consistency checks -------------------------------------------------------


def test_a_good_question_has_no_problems_of_its_own() -> None:
    report = check_questions([_q()], PAGES, PASSAGES)
    assert report.errors == []
    assert (report.answerable, report.unanswerable, report.total) == (1, 0, 1)


def test_duplicate_ids_and_placeholders_are_errors() -> None:
    report = check_questions(
        [_q("q1"), _q("q1", question="Another one?"), _q("q2", question="TODO: write a question")],
        PAGES,
    )
    assert "q1: duplicate id" in report.errors
    assert any(e.startswith("q2:") and "placeholder" in e for e in report.errors)


def test_unknown_files_and_missing_pages_are_errors() -> None:
    report = check_questions(
        [
            _q("q1", expected=[Evidence(source="missing.pdf", page=1)]),
            _q("q2", question="Q two?", expected=[Evidence(source="os.pdf", page=9)]),
        ],
        PAGES,
    )
    assert any("'missing.pdf' is not in the index" in e for e in report.errors)
    assert any("os.pdf has no indexed text on page 9" in e and "1-4" in e for e in report.errors)


def test_answerable_questions_need_pages_and_an_answer() -> None:
    report = check_questions([_q("q1", expected=[], reference_answer="  ")], PAGES)
    assert any("no expected pages" in e for e in report.errors)
    assert any("no reference_answer" in e for e in report.errors)


def test_unanswerable_questions_must_not_have_expected_pages() -> None:
    bad = _q("q1", type="unanswerable")
    good = EvalQuestion(id="q2", question="Capital of Australia?", type="unanswerable")
    errors = check_questions([bad], PAGES).errors
    assert any("unanswerable question has expected" in e for e in errors)
    assert check_questions([good], PAGES).errors == []


def test_drafts_that_still_need_review_are_errors() -> None:
    report = check_questions([_q(needs_review=True)], PAGES)
    assert any("needs_review" in e for e in report.errors)


def test_leftover_passage_field_is_a_warning() -> None:
    report = check_questions([_q(passage="copied lecture text")], PAGES)
    assert report.errors == []
    assert any("delete the `passage` field" in w for w in report.warnings)


def test_empty_keywords_are_errors() -> None:
    errors = check_questions([_q(keywords=["ok", " "])], PAGES).errors
    assert any("empty keyword" in e for e in errors)


def test_questions_copied_from_the_passage_get_a_warning() -> None:
    copied = _q(question="Only one thread at a time can enter the critical section?")
    report = check_questions([copied], PAGES, PASSAGES)
    assert any("copies wording" in w for w in report.warnings)
    own_words = _q(question="Why do I need a lock around shared data?")
    warnings = check_questions([own_words], PAGES, PASSAGES).warnings
    assert not any("copies wording" in w for w in warnings)


def test_repeated_question_text_is_a_warning() -> None:
    report = check_questions([_q("q1"), _q("q2")], PAGES)
    assert any("same question text" in w for w in report.warnings)


def test_size_advice() -> None:
    small = check_questions(_many(5), PAGES)
    assert any("only 5 questions" in w for w in small.warnings)
    enough = check_questions(_many(30), PAGES)
    assert not any("only" in w and "questions" in w for w in enough.warnings)


def test_balance_advice() -> None:
    questions = _many(30) + [
        _q("n1", question="Net one?", expected=[Evidence(source="net.md", page=1)]),
    ]
    report = check_questions(questions, PAGES)
    assert any("unanswerable question" in w for w in report.warnings)
    assert any("os.pdf supplies 30 of 31" in w for w in report.warnings)
    assert any("no follow-up" in w for w in report.warnings)


def test_a_balanced_set_has_no_warnings() -> None:
    questions: list[EvalQuestion] = []
    for i in range(24):
        source = "os.pdf" if i % 2 else "net.md"
        page = 1 + (i % 3) if source == "os.pdf" else 1
        evidence = [Evidence(source=source, page=page)]
        questions.append(_q(f"q{i}", question=f"Own words number {i}?", expected=evidence))
    questions += [
        EvalQuestion(id=f"u{i}", question=f"Outside the notes {i}?", type="unanswerable")
        for i in range(4)
    ]
    earlier = [ChatTurn(role="user", content="earlier")]
    for i, source in enumerate(["os.pdf", "net.md"]):
        evidence = [Evidence(source=source, page=1)]
        questions.append(
            _q(f"f{i}", question=f"Follow up {i}?", history=earlier, expected=evidence)
        )
    report = check_questions(questions, PAGES)
    assert report.errors == []
    assert report.warnings == []
    assert report.follow_ups == 2
    assert report.by_type["unanswerable"] == 4
