"""Load PDF, Markdown and text files into Document objects."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf

from vectornote.models import Document, Page

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".md", ".txt"})


class UnsupportedFileTypeError(ValueError):
    """The file extension is not one VectorNote can ingest."""


class DocumentLoadError(RuntimeError):
    """The file exists but could not be read (corrupt, encrypted, ...)."""


def _load_pdf(path: Path) -> list[Page]:
    try:
        with pymupdf.open(str(path)) as pdf:
            if pdf.needs_pass:
                raise DocumentLoadError(f"{path.name} is password protected")
            return [
                Page(number=index, text=page.get_text("text"))
                for index, page in enumerate(pdf, start=1)
            ]
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(f"Could not read {path.name}: {exc}") from exc


def _load_text(path: Path) -> list[Page]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return [Page(number=1, text=text)]


def load_document(path: Path, source: str | None = None) -> Document:
    """Load one file as raw pages (no cleaning).

    `source` is the name used in citations; it defaults to the file name.
    Markdown and text files are a single page.
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"Unsupported file type '{suffix}' (use {supported})")
    if not path.is_file():
        raise FileNotFoundError(path)

    pages = _load_pdf(path) if suffix == ".pdf" else _load_text(path)
    doc = Document(source=source or path.name, pages=pages)
    if not any(page.text.strip() for page in doc.pages):
        logger.warning("%s has no extractable text (scanned PDF? OCR is needed)", doc.source)
    return doc


def load_documents(directory: Path) -> list[Document]:
    """Load every supported file under `directory`, skipping hidden files."""
    docs: list[Document] = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if not path.is_file() or any(part.startswith(".") for part in relative.parts):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        docs.append(load_document(path, source=relative.as_posix()))
    return docs
