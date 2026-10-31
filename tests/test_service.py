from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from vectornote.config import Settings
from vectornote.embeddings.hashing import HashingEmbedder
from vectornote.ingestion.loaders import UnsupportedFileTypeError
from vectornote.service import IngestResult, RagService, safe_filename


class CountingEmbedder(HashingEmbedder):
    """Counts calls, and can be told to fail."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.fail = False

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding model crashed")
        return super().encode(texts)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        chroma_dir=tmp_path / "db",
        embedding_model="hashing",
    )


@pytest.fixture
def embedder() -> CountingEmbedder:
    return CountingEmbedder()


@pytest.fixture
def service(settings: Settings, embedder: CountingEmbedder) -> RagService:
    return RagService(settings, embedder=embedder)


def _search(service: RagService, text: str) -> list[str]:
    [vector] = service.embedder.encode([text])
    return [r.chunk.text for r in service.store.query(vector, 3)]


def test_ingest_new_file(service: RagService, tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("A mutex gives mutual exclusion.\nSemaphores count resources.")
    result = service.ingest_path(f)
    assert result.status == "added"
    assert result.chunks_added >= 1
    assert service.index_size() == result.chunks_added
    assert service.store.list_sources() == {"notes.txt": result.chunks_added}


def test_unchanged_file_is_skipped_without_embedding(
    service: RagService, embedder: CountingEmbedder, tmp_path: Path
) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("Paging splits memory into frames.")
    service.ingest_path(f)
    calls = embedder.calls
    again = service.ingest_path(f)
    assert again == IngestResult("notes.txt", "unchanged")
    assert embedder.calls == calls


def test_edited_file_replaces_old_chunks(service: RagService, tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("Deadlock needs four conditions.")
    service.ingest_path(f)
    f.write_text("Livelock keeps threads busy without progress.")
    result = service.ingest_path(f)
    assert result.status == "updated"
    assert service.index_size() == result.chunks_added
    assert _search(service, "livelock threads") == ["Livelock keeps threads busy without progress."]
    assert "Deadlock needs four conditions." not in _search(service, "deadlock")


def test_force_reindexes_unchanged_file(service: RagService, tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("Caches exploit locality.")
    service.ingest_path(f)
    assert service.ingest_path(f, force=True).status == "updated"
    assert service.index_size() == 1


def test_failed_embedding_keeps_the_old_index(
    service: RagService, embedder: CountingEmbedder, tmp_path: Path
) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("Original content about schedulers.")
    service.ingest_path(f)
    f.write_text("Edited content about schedulers and queues.")
    embedder.fail = True
    with pytest.raises(RuntimeError):
        service.ingest_path(f)
    embedder.fail = False
    assert _search(service, "schedulers") == ["Original content about schedulers."]


def test_empty_file_removes_old_chunks(service: RagService, tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("Something to index.")
    service.ingest_path(f)
    f.write_text("   \n")
    assert service.ingest_path(f).status == "empty"
    assert service.index_size() == 0


def test_ingest_directory_reports_each_file(service: RagService, settings: Settings) -> None:
    data = settings.data_dir
    (data / "sub").mkdir(parents=True)
    (data / "a.txt").write_text("Alpha notes about threads.")
    (data / "sub" / "b.md").write_text("# Beta\n\nNotes about mutexes.")
    (data / "broken.pdf").write_bytes(b"not a pdf")
    (data / "image.png").write_bytes(b"ignored")

    results = {r.source: r for r in service.ingest_directory(data)}
    assert set(results) == {"a.txt", "sub/b.md", "broken.pdf"}
    assert results["a.txt"].status == "added"
    assert results["sub/b.md"].status == "added"
    assert results["broken.pdf"].status == "failed"
    assert results["broken.pdf"].error
    assert set(service.store.list_sources()) == {"a.txt", "sub/b.md"}


def test_second_directory_run_is_all_unchanged(service: RagService, settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "a.txt").write_text("Alpha notes.")
    (settings.data_dir / "b.txt").write_text("Beta notes.")
    list(service.ingest_directory(settings.data_dir))
    again = list(service.ingest_directory(settings.data_dir))
    assert [r.status for r in again] == ["unchanged", "unchanged"]


def test_prune_removes_deleted_files(service: RagService, settings: Settings) -> None:
    data = settings.data_dir
    data.mkdir(parents=True)
    (data / "keep.txt").write_text("Keep me.")
    (data / "gone.txt").write_text("Delete me.")
    list(service.ingest_directory(data))
    (data / "gone.txt").unlink()

    results = list(service.ingest_directory(data, prune=True))
    assert IngestResult("gone.txt", "removed") in results
    assert list(service.store.list_sources()) == ["keep.txt"]


def test_prune_requires_an_existing_directory(service: RagService, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list(service.ingest_directory(tmp_path / "missing", prune=True))


def test_upload_is_saved_and_ingested(service: RagService, settings: Settings) -> None:
    result = service.ingest_upload("lecture notes.txt", b"Page replacement policies.")
    assert result.status == "added"
    assert (settings.data_dir / "lecture notes.txt").read_bytes() == b"Page replacement policies."
    assert service.ingest_upload("lecture notes.txt", b"Page replacement policies.").status == (
        "unchanged"
    )
    assert [p.name for p in settings.data_dir.iterdir()] == ["lecture notes.txt"]


def test_upload_cannot_escape_the_data_directory(
    service: RagService, settings: Settings, tmp_path: Path
) -> None:
    service.ingest_upload("../../evil.txt", b"text")
    assert (settings.data_dir / "evil.txt").exists()
    assert not (tmp_path / "evil.txt").exists()


def test_unsupported_upload_is_rejected(service: RagService, settings: Settings) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        service.ingest_upload("virus.exe", b"MZ")
    assert not settings.data_dir.exists() or not list(settings.data_dir.iterdir())


def test_corrupt_upload_does_not_replace_a_good_file(
    service: RagService, settings: Settings
) -> None:
    service.ingest_upload("slides.md", b"Good content about caches.")
    with pytest.raises(UnsupportedFileTypeError):
        service.ingest_upload("slides.exe", b"junk")
    assert (settings.data_dir / "slides.md").read_bytes() == b"Good content about caches."
    assert sorted(p.name for p in settings.data_dir.iterdir()) == ["slides.md"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("notes.pdf", "notes.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\cours réseau.pdf", "cours réseau.pdf"),
        ("a/b/c.md", "c.md"),
        (".hidden.txt", "hidden.txt"),
        ("we<ird>*name?.txt", "we_ird__name_.txt"),
        ("", "upload"),
        ("...", "upload"),
    ],
)
def test_safe_filename(raw: str, expected: str) -> None:
    assert safe_filename(raw) == expected


def test_search_uses_the_default_top_k_and_filters(
    service: RagService, settings: Settings
) -> None:
    data = settings.data_dir
    data.mkdir(parents=True)
    (data / "os.txt").write_text("A mutex gives mutual exclusion to a critical section.")
    (data / "net.txt").write_text("A subnet mask separates network and host bits.")
    list(service.ingest_directory(data))

    results = service.search("mutex critical section")
    assert results[0].chunk.source == "os.txt"
    assert len(results) == 2  # fewer chunks than the default top_k
    assert len(service.search("mutex", top_k=1)) == 1
    only_net = service.search("mutex", sources=["net.txt"])
    assert {r.chunk.source for r in only_net} == {"net.txt"}
    assert service.indexed_sources() == {"net.txt": 1, "os.txt": 1}
