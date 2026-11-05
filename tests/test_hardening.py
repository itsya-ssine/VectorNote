"""Uploads and file names under hostile or careless input."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, MutableMapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vectornote.api.app import create_app
from vectornote.api.deps import get_settings
from vectornote.api.limits import UploadSizeLimit
from vectornote.config import Settings
from vectornote.ingestion.loaders import DocumentLoadError, load_document
from vectornote.service import MAX_NAME_BYTES, safe_filename

MB = 1024 * 1024


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(tmp_path: Path, data_dir: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        data_dir=data_dir,
        chroma_dir=tmp_path / "db",
        embedding_model="hashing",
        max_upload_mb=1,
    )
    return TestClient(app)


def upload(client: TestClient, name: str, content: bytes) -> Any:
    return client.post("/ingest", files={"file": (name, content, "text/plain")})


def leftovers(data_dir: Path) -> list[str]:
    """Temporary upload files that should never outlive a request."""
    return sorted(p.name for p in data_dir.glob(".upload-*")) if data_dir.exists() else []


# ---- upload size ---------------------------------------------------------


def test_default_limit_is_50_mb_and_can_be_set(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().max_upload_mb == 50
    assert Settings().max_upload_bytes == 50 * MB
    monkeypatch.setenv("VECTORNOTE_MAX_UPLOAD_MB", "5")
    assert Settings().max_upload_mb == 5


def test_oversized_upload_is_refused_before_anything_is_stored(
    client: TestClient, data_dir: Path
) -> None:
    r = upload(client, "big.txt", b"word " * (2 * MB // 5))
    assert r.status_code == 413
    assert r.json() == {"detail": "File is too large (the limit is 1 MB)."}
    assert not data_dir.exists() or list(data_dir.iterdir()) == []


def test_upload_exactly_at_the_limit_is_accepted(client: TestClient) -> None:
    r = upload(client, "edge.txt", b"a" * MB)
    assert r.status_code == 200


def test_one_byte_over_the_limit_is_refused_by_the_route(client: TestClient) -> None:
    # Small enough to pass the Content-Length pre-check (which allows for multipart framing),
    # so this exercises the check after reading.
    r = upload(client, "edge.txt", b"a" * (MB + 1))
    assert r.status_code == 413


def test_upload_without_content_length_is_still_limited(
    client: TestClient, data_dir: Path
) -> None:
    boundary = "TESTBOUNDARY"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()

    def body() -> Iterator[bytes]:  # a generator makes the request chunked: no Content-Length
        yield head
        for _ in range(3):
            yield b"a" * MB
        yield tail

    r = client.post(
        "/ingest",
        content=body(),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    assert r.status_code == 413
    assert leftovers(data_dir) == []


def test_refusal_carries_cors_headers_so_the_browser_can_show_it(client: TestClient) -> None:
    r = client.post(
        "/ingest",
        files={"file": ("big.txt", b"a" * (2 * MB), "text/plain")},
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 413
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def run_middleware(path: str, method: str, content_length: str | None) -> tuple[list[int], bool]:
    """Send one request through UploadSizeLimit(limit 1 MB); report statuses and inner calls."""
    called = False
    statuses: list[int] = []

    async def inner(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    async def receive() -> MutableMapping[str, Any]:
        return {"type": "http.request", "body": b"x" * 10, "more_body": False}

    async def send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    headers = [(b"content-length", content_length.encode())] if content_length else []
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    asyncio.run(UploadSizeLimit(inner, lambda: 1)(scope, receive, send))
    return statuses, called


def test_middleware_only_guards_uploads_that_declare_a_big_body() -> None:
    assert run_middleware("/ingest", "POST", str(5 * MB)) == ([413], False)
    assert run_middleware("/ingest", "POST", str(MB)) == ([], True)
    assert run_middleware("/ingest", "POST", None) == ([], True)
    assert run_middleware("/ingest", "POST", "not a number") == ([], True)
    assert run_middleware("/ask", "POST", str(5 * MB)) == ([], True)
    assert run_middleware("/ingest", "GET", str(5 * MB)) == ([], True)


# ---- file names ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("notes.md", "notes.md"),
        ("../../etc/passwd.md", "passwd.md"),
        ("..\\..\\windows\\evil.txt", "evil.txt"),
        (".hidden.md", "hidden.md"),
        ("my notes (v2).txt", "my notes (v2).txt"),
        ("we!ird$name.md", "we_ird_name.md"),
        ("nul\x00byte.txt", "nul_byte.txt"),
        ("cours_é_ملخص.md", "cours_é_ملخص.md"),
        ("", "upload"),
        ("...", "upload"),
        ("   ", "upload"),
    ],
)
def test_safe_filename(raw: str, expected: str) -> None:
    assert safe_filename(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "a" * 300 + ".md",
        "a" * 300,
        "é" * 300 + ".pdf",
        "ملخص" * 80 + ".txt",
        "x" * 199 + ".md",
        "b" * 190 + "." + "c" * 60,
    ],
)
def test_long_names_are_shortened_to_a_safe_length(raw: str) -> None:
    name = safe_filename(raw)
    assert 0 < len(name.encode()) <= MAX_NAME_BYTES
    assert safe_filename(name) == name  # stable, which delete relies on
    suffix = Path(raw).suffix
    if suffix and len(suffix.encode()) < 20:
        assert name.endswith(suffix)


def test_long_file_name_uploads_and_deletes(client: TestClient, data_dir: Path) -> None:
    r = upload(client, "a" * 300 + ".md", b"A mutex gives mutual exclusion.")
    assert r.status_code == 200
    name = r.json()["filename"]
    assert name.endswith(".md") and len(name.encode()) <= MAX_NAME_BYTES
    assert [d["name"] for d in client.get("/documents").json()] == [name]
    assert client.delete(f"/documents/{name}").status_code == 200
    assert client.get("/documents").json() == []


@pytest.mark.parametrize("name", ["../../evil.md", "..\\..\\evil.md", "/etc/cron.d/evil.md"])
def test_uploads_cannot_leave_the_data_directory(
    client: TestClient, tmp_path: Path, data_dir: Path, name: str
) -> None:
    assert upload(client, name, b"A mutex.").status_code == 200
    assert sorted(p.name for p in data_dir.iterdir()) == ["evil.md"]
    assert not (tmp_path / "evil.md").exists()


# ---- unreadable files ----------------------------------------------------


@pytest.mark.parametrize("payload", [b"%PDF-1.4 garbage", b""])
def test_unreadable_pdf_error_names_the_file_not_the_server(
    client: TestClient, data_dir: Path, payload: bytes
) -> None:
    r = upload(client, "lecture.pdf", payload)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "lecture.pdf" in detail
    assert ".upload-" not in detail
    assert str(data_dir) not in detail
    assert leftovers(data_dir) == []
    assert not (data_dir / "lecture.pdf").exists()


def test_loader_errors_use_the_source_name(tmp_path: Path) -> None:
    broken = tmp_path / ".upload-abc123.pdf"
    broken.write_bytes(b"%PDF-1.4 garbage")
    with pytest.raises(DocumentLoadError) as caught:
        load_document(broken, source="lecture.pdf")
    message = str(caught.value)
    assert "lecture.pdf" in message
    assert ".upload-abc123" not in message
    assert str(tmp_path) not in message


def test_a_failed_upload_does_not_replace_the_existing_file(
    client: TestClient, data_dir: Path
) -> None:
    assert upload(client, "notes.pdf", b"").status_code == 422
    assert upload(client, "notes.txt", b"A mutex gives mutual exclusion.").status_code == 200
    assert upload(client, "notes.txt", b"").json()["status"] == "empty"
    assert leftovers(data_dir) == []


# ---- concurrency ---------------------------------------------------------


def test_parallel_uploads_are_all_stored_and_indexed(
    client: TestClient, data_dir: Path
) -> None:
    def send(i: int) -> int:
        text = f"Document {i} explains why mutex number {i} protects shared data. " * 10
        return int(upload(client, f"doc{i}.md", text.encode()).status_code)

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(send, range(8)))
    assert codes == [200] * 8
    names = sorted(d["name"] for d in client.get("/documents").json())
    assert names == [f"doc{i}.md" for i in range(8)]
    assert leftovers(data_dir) == []
    for i in range(8):  # every file really is in the index
        hits = client.delete(f"/documents/doc{i}.md").json()["chunks_removed"]
        assert hits >= 1
