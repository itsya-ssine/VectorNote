from __future__ import annotations

from pathlib import Path

import pytest

from tests.pdf_helpers import make_pdf
from vectornote.ingestion.cleaning import clean_document
from vectornote.ingestion.loaders import (
    DocumentLoadError,
    UnsupportedFileTypeError,
    load_document,
    load_documents,
)


def test_load_txt(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello world", encoding="utf-8")
    doc = load_document(f)
    assert doc.source == "notes.txt"
    assert [(p.number, p.text) for p in doc.pages] == [(1, "hello world")]


def test_load_markdown_strips_bom(tmp_path: Path) -> None:
    f = tmp_path / "notes.md"
    f.write_bytes(b"\xef\xbb\xbf# Title\n\nBody")
    assert load_document(f).pages[0].text == "# Title\n\nBody"


def test_load_pdf_keeps_page_numbers(tmp_path: Path) -> None:
    f = make_pdf(tmp_path / "lecture.pdf", ["alpha page", "beta page", "gamma page"])
    doc = load_document(f)
    assert [p.number for p in doc.pages] == [1, 2, 3]
    assert "beta page" in doc.pages[1].text


def test_pdf_header_footer_removed_after_cleaning(tmp_path: Path) -> None:
    topics = [
        "threads", "mutexes", "semaphores", "deadlocks", "paging", "caching", "disks", "files"
    ]
    bodies = [f"Notes about {topic}" for topic in topics]
    f = make_pdf(
        tmp_path / "lecture.pdf",
        bodies,
        header="Operating Systems - Lecture 5",
        footer="Page {n} of {total}",
    )
    raw = load_document(f)
    assert "Operating Systems" in raw.pages[0].text
    cleaned = clean_document(raw)
    for page in cleaned.pages:
        assert "Operating Systems" not in page.text
        assert "Page" not in page.text
        assert page.text == bodies[page.number - 1]


def test_blank_pdf_pages_are_dropped_with_numbers_preserved(tmp_path: Path) -> None:
    f = make_pdf(tmp_path / "gaps.pdf", ["first", "", "third"])
    cleaned = clean_document(load_document(f))
    assert [p.number for p in cleaned.pages] == [1, 3]


def test_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "image.png"
    f.write_bytes(b"x")
    with pytest.raises(UnsupportedFileTypeError):
        load_document(f)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_document(tmp_path / "nope.pdf")


def test_corrupt_pdf_raises_load_error(tmp_path: Path) -> None:
    f = tmp_path / "broken.pdf"
    f.write_bytes(b"this is not a pdf")
    with pytest.raises(DocumentLoadError):
        load_document(f)


def test_load_documents_walks_directory(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("b")
    (tmp_path / "skip.png").write_bytes(b"x")
    (tmp_path / ".hidden.txt").write_text("h")
    docs = load_documents(tmp_path)
    assert [d.source for d in docs] == ["a.txt", "sub/b.md"]
