"""A client that goes away mid-answer must stop the model.

This needs a real HTTP server: the in-process test client cannot disconnect.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from tests.fakes import FakeLLM
from vectornote.api.app import create_app
from vectornote.api.deps import get_service
from vectornote.config import Settings
from vectornote.embeddings.hashing import HashingEmbedder
from vectornote.service import RagService

REPLY = "one two three four five six seven eight nine ten eleven twelve [1]"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[str, FakeLLM]]:
    settings = Settings(
        data_dir=tmp_path / "data", chroma_dir=tmp_path / "db", embedding_model="hashing"
    )
    llm = FakeLLM(REPLY)
    llm.delay = 0.2
    service = RagService(settings, embedder=HashingEmbedder(), llm=llm)
    settings.data_dir.mkdir()
    note = "A mutex gives mutual exclusion to a critical section."
    (settings.data_dir / "os.txt").write_text(note)
    list(service.ingest_directory(settings.data_dir))

    app = create_app()
    app.dependency_overrides[get_service] = lambda: service
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "test server did not start"
    try:
        yield f"http://127.0.0.1:{port}", llm
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_disconnecting_stops_the_model_early(served: tuple[str, FakeLLM]) -> None:
    url, llm = served
    body = {"question": "How does a mutex protect a critical section?"}
    with httpx.stream("POST", f"{url}/ask/stream", json=body, timeout=15) as response:
        for line in response.iter_lines():
            if line.startswith("event: token"):
                break  # read one token, then walk away

    deadline = time.time() + 5
    while not llm.stream_closed and time.time() < deadline:
        time.sleep(0.05)
    assert llm.stream_closed, "the model stream was left open after the client disconnected"
    assert llm.pieces_sent < len(REPLY.split()), "the model kept generating for nobody"


def test_a_complete_answer_over_real_http(served: tuple[str, FakeLLM]) -> None:
    url, llm = served
    llm.delay = 0.0
    body = {"question": "How does a mutex protect a critical section?"}
    with httpx.stream("POST", f"{url}/ask/stream", json=body, timeout=15) as response:
        text = "".join(response.iter_text())
    assert text.count("event: token") == len(REPLY.split())
    assert text.rstrip().splitlines()[-2] == "event: done"
