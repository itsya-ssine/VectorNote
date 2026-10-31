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
    app.dependency_overrides[get_settings] = lambda: Settings(
        data_dir=tmp_path / "data",
        chroma_dir=tmp_path / "db",
        embedding_model="hashing",
    )
    yield TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_documents_lists_data_dir(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "notes.md").write_text("hello")
    (tmp_path / "data" / ".gitkeep").write_text("")
    r = client.get("/documents")
    assert r.status_code == 200
    assert r.json() == [{"name": "notes.md", "size_bytes": 5}]


def test_ask_not_implemented_yet(client: TestClient) -> None:
    r = client.post("/ask", json={"question": "What is a mutex?"})
    assert r.status_code == 501


def test_ask_validates_input(client: TestClient) -> None:
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 422


def test_ingest_upload_then_unchanged(client: TestClient) -> None:
    files = {"file": ("notes.txt", b"A mutex gives mutual exclusion.", "text/plain")}
    first = client.post("/ingest", files=files)
    assert first.status_code == 200
    assert first.json()["status"] == "added"
    assert first.json()["chunks_added"] >= 1
    assert first.json()["filename"] == "notes.txt"

    second = client.post("/ingest", files=files)
    assert second.status_code == 200
    assert second.json() == {"filename": "notes.txt", "status": "unchanged", "chunks_added": 0}

    listed = client.get("/documents").json()
    assert [d["name"] for d in listed] == ["notes.txt"]


def test_ingest_rejects_unsupported_type(client: TestClient) -> None:
    r = client.post("/ingest", files={"file": ("setup.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_ingest_rejects_corrupt_pdf(client: TestClient) -> None:
    r = client.post("/ingest", files={"file": ("broken.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 422
