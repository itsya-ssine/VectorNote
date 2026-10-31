from __future__ import annotations

from pathlib import Path

import pytest

from vectornote.cli import main


def test_inspect_prints_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("A mutex gives mutual exclusion.")
    assert main(["inspect", str(f)]) == 0
    out = capsys.readouterr().out
    assert "notes.txt: 1 page(s) loaded, 1 kept" in out
    assert "mutual exclusion" in out


def test_inspect_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(tmp_path / "missing.pdf")]) == 2
    assert "error" in capsys.readouterr().err


def test_inspect_with_chunks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "notes.md"
    f.write_text("\n".join(f"Line {i} about threads and locks." for i in range(200)))
    assert main(["inspect", str(f), "--chunks"]) == 0
    out = capsys.readouterr().out
    assert "chunks (size=800, overlap=100)" in out
    assert "notes.md#p1-c0-" in out


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("VECTORNOTE_DATA_DIR", str(data))
    monkeypatch.setenv("VECTORNOTE_CHROMA_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "hashing")
    return data


def test_ingest_data_directory_then_skip_unchanged(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (workspace / "a.txt").write_text("Threads share an address space.")
    (workspace / "b.md").write_text("# Locks\n\nA mutex protects shared data.")

    assert main(["ingest"]) == 0
    first = capsys.readouterr().out
    assert "added      a.txt" in first
    assert "added      b.md" in first
    assert "2 added" in first

    assert main(["ingest"]) == 0
    assert "2 unchanged" in capsys.readouterr().out

    assert main(["ingest", "--force"]) == 0
    assert "2 updated" in capsys.readouterr().out


def test_ingest_reports_failures_with_exit_code_1(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (workspace / "ok.txt").write_text("Fine file.")
    (workspace / "broken.pdf").write_bytes(b"not a pdf")
    assert main(["ingest"]) == 1
    out = capsys.readouterr().out
    assert "failed     broken.pdf" in out
    assert "added      ok.txt" in out


def test_ingest_single_file(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "outside.txt"
    f.write_text("A file from anywhere.")
    assert main(["ingest", str(f)]) == 0
    assert "added      outside.txt" in capsys.readouterr().out


def test_ingest_prune(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (workspace / "keep.txt").write_text("Keep.")
    (workspace / "gone.txt").write_text("Gone soon.")
    main(["ingest"])
    (workspace / "gone.txt").unlink()
    capsys.readouterr()
    assert main(["ingest", "--prune"]) == 0
    assert "removed    gone.txt" in capsys.readouterr().out


def test_ingest_prune_with_paths_is_refused(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ingest", str(workspace), "--prune"]) == 2
    assert "--prune" in capsys.readouterr().err


def test_ingest_missing_path(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ingest", str(workspace / "nope.pdf")]) == 2
    assert "not found" in capsys.readouterr().err


@pytest.fixture
def indexed(workspace: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    (workspace / "os.txt").write_text("A mutex gives mutual exclusion to a critical section.")
    (workspace / "net.md").write_text("A subnet mask separates network and host bits.")
    assert main(["ingest"]) == 0
    capsys.readouterr()
    return workspace


def test_search_prints_ranked_results(indexed: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "how does a mutex work in a critical section"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(" 1. ")
    first_line = out.splitlines()[0]
    assert "os.txt, p. 1" in first_line
    assert "mutual exclusion" in out


def test_search_limits_and_filters(indexed: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "mask", "-k", "1", "--source", "net.md"]) == 0
    out = capsys.readouterr().out
    assert "net.md, p. 1" in out
    assert "os.txt" not in out
    assert " 2. " not in out


def test_search_min_score_can_return_nothing(
    indexed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["search", "zebra giraffe", "--min-score", "0.9"]) == 0
    assert "No results." in capsys.readouterr().out


def test_search_unknown_source(indexed: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "mutex", "--source", "missing.pdf"]) == 2
    err = capsys.readouterr().err
    assert "not indexed: missing.pdf" in err
    assert "os.txt" in err


def test_search_on_empty_index(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "mutex"]) == 1
    assert "vectornote ingest" in capsys.readouterr().err


def test_search_blank_query(indexed: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "  "]) == 2
    assert "empty" in capsys.readouterr().err


def test_switching_embedding_model_gives_a_clear_error(
    indexed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VECTORNOTE_EMBEDDING_MODEL", "some/other-model")
    assert main(["search", "mutex"]) == 2
    err = capsys.readouterr().err
    assert "built with 'hashing'" in err
    assert "ingest again" in err
