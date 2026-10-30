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
