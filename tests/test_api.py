from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vectornote.api.app import create_app
from vectornote.api.deps import get_settings
from vectornote.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=tmp_path)
    yield TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_documents_lists_data_dir(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("hello")
    (tmp_path / ".gitkeep").write_text("")
    r = client.get("/documents")
    assert r.status_code == 200
    assert r.json() == [{"name": "notes.md", "size_bytes": 5}]


def test_ask_not_implemented_yet(client: TestClient) -> None:
    r = client.post("/ask", json={"question": "What is a mutex?"})
    assert r.status_code == 501


def test_ask_validates_input(client: TestClient) -> None:
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 422
