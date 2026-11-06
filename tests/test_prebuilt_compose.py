"""The compose file that runs published images must follow docker-compose.yml."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "make_prebuilt_compose.py"


def test_prebuilt_compose_is_up_to_date() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_prebuilt_compose_pulls_images_instead_of_building() -> None:
    text = (ROOT / "docker-compose.prebuilt.yml").read_text()
    assert "build:" not in text.replace("# GENERATED", "")
    assert "ghcr.io/itsya-ssine/vectornote-api:${VECTORNOTE_VERSION:-latest}" in text
    assert "ghcr.io/itsya-ssine/vectornote-web:${VECTORNOTE_VERSION:-latest}" in text
    assert "ollama/ollama" in text  # the rest of the stack is unchanged


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_prebuilt_compose", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_reports_a_stale_file_and_the_script_repairs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_script()
    stale = tmp_path / "docker-compose.prebuilt.yml"
    stale.write_text("an old version\n")
    monkeypatch.setattr(module, "TARGET", stale)

    monkeypatch.setattr(sys, "argv", ["make_prebuilt_compose.py", "--check"])
    assert module.main() == 1

    monkeypatch.setattr(sys, "argv", ["make_prebuilt_compose.py"])
    assert module.main() == 0
    assert stale.read_text() == (ROOT / "docker-compose.prebuilt.yml").read_text()

    monkeypatch.setattr(sys, "argv", ["make_prebuilt_compose.py", "--check"])
    assert module.main() == 0


def test_render_refuses_a_compose_file_without_the_build_lines() -> None:
    module = load_script()
    ok = "name: x\nservices:\n  api:\n    build: .\n  web:\n    build: ./web\n"
    assert "vectornote-api" in module.render(ok)
    with pytest.raises(SystemExit, match="no longer has"):
        module.render("name: x\nservices: {}\n")
