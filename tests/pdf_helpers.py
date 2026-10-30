"""Helpers to build small PDFs for tests."""

from __future__ import annotations

from pathlib import Path

import pymupdf


def make_pdf(
    path: Path,
    bodies: list[str],
    header: str | None = None,
    footer: str | None = None,
) -> Path:
    """Write a PDF with one body per page.

    `footer` may contain `{n}` (page number) and `{total}` (page count).
    """
    pdf = pymupdf.open()
    total = len(bodies)
    for n, body in enumerate(bodies, start=1):
        page = pdf.new_page()
        if header:
            page.insert_text((72, 40), header, fontsize=9)
        if body:
            page.insert_text((72, 120), body, fontsize=11)
        if footer:
            page.insert_text((72, 800), footer.format(n=n, total=total), fontsize=9)
    pdf.save(str(path))
    pdf.close()
    return path
