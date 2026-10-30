from __future__ import annotations

import pytest

from vectornote import __version__
from vectornote.cli import main
from vectornote.config import Settings


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_default_settings() -> None:
    s = Settings()
    assert s.chunk_overlap < s.chunk_size
    assert s.top_k > 0


def test_cli_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "vectornote" in capsys.readouterr().out
