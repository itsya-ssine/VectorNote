from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_eval_runner import ScriptedLLM
from vectornote.cli import main

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "eval" / "example"
QUESTIONS = str(EXAMPLE / "questions.example.jsonl")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VECTORNOTE_DATA_DIR", str(EXAMPLE / "corpus"))
    monkeypatch.setenv("VECTORNOTE_CHROMA_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "hashing")
    assert main(["ingest"]) == 0
    return tmp_path


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> ScriptedLLM:
    fake = ScriptedLLM("A mutex gives mutual exclusion to a critical section [1].")
    monkeypatch.setattr("vectornote.service.OllamaClient", lambda url, model: fake)
    return fake


def test_run_measures_every_mode_by_default(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert main(["eval", "run", QUESTIONS]) == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "Retrieval, top 5 (10 answerable, 3 unanswerable; 2 follow-up(s) skipped" in out
    for mode in ("vector", "bm25", "hybrid"):
        assert mode in out
    assert "hit@1" in out and "MRR" in out
    assert "Relevance threshold" in out
    assert "(current)" in out
    assert "Answers" not in out  # needs --answers
    assert "Measuring retrieval (bm25)" in captured.err  # progress goes to stderr


def test_run_can_measure_one_mode_at_another_depth(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert main(["eval", "run", QUESTIONS, "--mode", "bm25", "-k", "3"]) == 0
    out = capsys.readouterr().out
    assert "top 3" in out
    assert "hit@3" in out and "hit@5" not in out
    assert "bm25" in out and "vector" not in out
    assert "Relevance threshold" not in out  # keyword search has no cosine threshold


def test_markdown_output_is_clean_enough_to_redirect_into_a_file(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert main(["eval", "run", QUESTIONS, "--format", "markdown", "--mode", "hybrid"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("Measured on 15 questions with `hashing`")
    assert "| mode | hit@1 | hit@3 | hit@5 | MRR | p50 ms | p95 ms |" in captured.out
    assert "Measuring" not in captured.out  # progress is on stderr only


def test_run_saves_the_full_results_as_json(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "results" / "run.json"
    assert main(["eval", "run", QUESTIONS, "-o", str(target)]) == 0
    assert "Saved the full results" in capsys.readouterr().err
    data = json.loads(target.read_text(encoding="utf-8"))
    assert [r["mode"] for r in data["retrieval"]] == ["vector", "bm25", "hybrid"]
    assert data["info"]["questions"] == 15
    assert data["info"]["chunk_size"] == 800
    assert data["answers"] is None and data["answer_records"] == []


def test_run_rewrites_follow_ups_when_asked(
    workspace: Path, llm: ScriptedLLM, capsys: pytest.CaptureFixture[str]
) -> None:
    llm.rewrite_reply = "What is a mutex?"
    capsys.readouterr()
    assert main(["eval", "run", QUESTIONS, "--rewrite", "--mode", "hybrid"]) == 0
    out = capsys.readouterr().out
    assert "12 answerable, 3 unanswerable" in out
    assert "skipped" not in out
    assert len(llm.rewrite_calls) == 2


def test_run_with_answers_and_judge(
    workspace: Path,
    tmp_path: Path,
    llm: ScriptedLLM,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "answers.json"
    capsys.readouterr()
    code = main(
        ["eval", "run", QUESTIONS, "--mode", "hybrid", "--answers", "--judge", "-o", str(target)]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "Answers (hybrid search, model llama3.2:3b)" in captured.out
    assert "faithfulness (model judge)" in captured.out
    assert "judged)" in captured.out
    assert "15/15" in captured.err  # progress
    assert llm.judged >= 1

    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data["answer_records"]) == 15  # follow-ups are answered too
    assert data["answers"]["answerable"] == 12
    assert any(r["answer"] for r in data["answer_records"])


def test_judge_needs_answers(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["eval", "run", QUESTIONS, "--judge"]) == 2
    assert "--judge needs --answers" in capsys.readouterr().err


def test_top_k_must_be_positive(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["eval", "run", QUESTIONS, "-k", "0"]) == 2
    assert "--top-k" in capsys.readouterr().err


def test_run_refuses_a_question_file_with_errors(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.jsonl"
    rows = [
        {"id": f"q{i}", "question": "What is a TLB?", "type": "definition",
         "expected": [{"source": "os-lecture.pdf", "page": 90 + i}], "reference_answer": "A cache."}
        for i in range(7)
    ]
    bad.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    capsys.readouterr()
    assert main(["eval", "run", str(bad)]) == 1
    captured = capsys.readouterr()
    assert "would be meaningless" in captured.err
    assert "no indexed text on page 90" in captured.err
    assert "and 2 more" in captured.err  # only the first five are listed
    assert "vectornote eval check" in captured.err
    assert captured.out == ""


def test_run_reports_unreadable_or_empty_question_files(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["eval", "run", str(tmp_path / "missing.jsonl")]) == 2
    assert "error" in capsys.readouterr().err
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n")
    assert main(["eval", "run", str(empty)]) == 2
    assert "has no questions" in capsys.readouterr().err


def test_run_needs_an_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VECTORNOTE_CHROMA_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "hashing")
    assert main(["eval", "run", QUESTIONS]) == 1
    assert "vectornote ingest" in capsys.readouterr().err
