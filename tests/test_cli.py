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
