from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes import FakeLLM
from vectornote.cli import main
from vectornote.evaluation import load_questions

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "eval" / "example"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VECTORNOTE_DATA_DIR", str(EXAMPLE / "corpus"))
    monkeypatch.setenv("VECTORNOTE_CHROMA_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "hashing")
    assert main(["ingest"]) == 0
    return tmp_path


def test_the_example_questions_are_valid_for_the_example_corpus(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert main(["eval", "check", str(EXAMPLE / "questions.example.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "15 questions" in out
    assert "answerable 12, unanswerable 3 (20%), follow-ups 2" in out
    assert "languages: en 10, fr 5" in out
    assert "Errors" not in out
    assert "only 15 questions" in out  # advice, not an error


def test_the_example_corpus_loads_as_expected(workspace: Path) -> None:
    from vectornote.config import Settings
    from vectornote.service import RagService

    sources = RagService(Settings()).indexed_sources()
    assert set(sources) == {"os-lecture.pdf", "reseaux.md"}
    chunks = RagService(Settings()).indexed_chunks()
    pdf_pages = {c.page for c in chunks if c.source == "os-lecture.pdf"}
    assert pdf_pages == {1, 2, 3, 4, 5, 6}
    # the running header and footer were removed by the cleaning step
    assert not any("Lecture 5" in c.text or "Page 3 of" in c.text for c in chunks)


def test_check_reports_errors_with_exit_code_1(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.jsonl"
    rows = [
        {"id": "q1", "question": "What is a TLB?", "type": "definition",
         "expected": [{"source": "os-lecture.pdf", "page": 99}], "reference_answer": "A cache."},
        {"id": "q1", "question": "TODO: write one",
         "expected": [{"source": "nope.pdf", "page": 1}]},
    ]
    bad.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    capsys.readouterr()
    assert main(["eval", "check", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "Errors" in out
    assert "has no indexed text on page 99" in out
    assert "duplicate id" in out
    assert "'nope.pdf' is not in the index" in out
    assert "OK" not in out


def test_check_reports_unreadable_files(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["eval", "check", str(tmp_path / "missing.jsonl")]) == 2
    assert "error" in capsys.readouterr().err
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{nope}\n")
    assert main(["eval", "check", str(broken)]) == 2
    assert "broken.jsonl:1" in capsys.readouterr().err


def test_scaffold_writes_drafts_that_check_then_complains_about(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "eval" / "draft.jsonl"
    assert main(["eval", "scaffold", "-n", "5", "-o", str(out_file)]) == 0
    printed = capsys.readouterr().out
    assert "Wrote 5 drafts" in printed
    assert "eval check" in printed

    drafts = load_questions(out_file)
    assert len(drafts) == 5
    assert all(d.passage for d in drafts)
    assert {e.source for d in drafts for e in d.expected} == {"os-lecture.pdf", "reseaux.md"}

    assert main(["eval", "check", str(out_file)]) == 1
    assert "placeholder" in capsys.readouterr().out


def test_scaffold_will_not_overwrite_without_force(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "draft.jsonl"
    target.write_text("keep me\n")
    assert main(["eval", "scaffold", "-n", "3", "-o", str(target)]) == 2
    assert "--force" in capsys.readouterr().err
    assert target.read_text() == "keep me\n"
    assert main(["eval", "scaffold", "-n", "3", "-o", str(target), "--force"]) == 0
    assert len(load_questions(target)) == 3


def test_scaffold_rejects_a_bad_count(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["eval", "scaffold", "-n", "0", "-o", str(tmp_path / "d.jsonl")]) == 2
    assert "--count" in capsys.readouterr().err


def test_scaffold_with_suggestions_asks_the_model_and_marks_drafts_for_review(
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    llm = FakeLLM()
    llm.rewrite_reply = ""
    monkeypatch.setattr("vectornote.service.OllamaClient", lambda url, model: llm)
    llm.complete = lambda messages, max_tokens=None: json.dumps(  # type: ignore[method-assign]
        {"question": "Why use a lock?", "answer": "To protect shared data."}
    )
    out_file = tmp_path / "suggested.jsonl"
    assert main(["eval", "scaffold", "-n", "3", "-o", str(out_file), "--suggest"]) == 0
    drafts = load_questions(out_file)
    assert all(d.question == "Why use a lock?" and d.needs_review for d in drafts)
    capsys.readouterr()
    assert main(["eval", "check", str(out_file)]) == 1
    assert "needs_review" in capsys.readouterr().out


def test_scaffold_needs_an_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VECTORNOTE_CHROMA_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "hashing")
    assert main(["eval", "scaffold", "-o", str(tmp_path / "d.jsonl")]) == 1
    assert "vectornote ingest" in capsys.readouterr().err
