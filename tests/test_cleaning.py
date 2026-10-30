from __future__ import annotations

import pytest

from vectornote.ingestion.cleaning import (
    clean_document,
    clean_text,
    find_repeated_signatures,
    strip_repeated_lines,
)
from vectornote.models import Document, Page


def test_ligatures_and_soft_hyphen() -> None:
    assert clean_text("e\ufb03cient \ufb01le\u00ad system") == "efficient file system"


def test_hyphenated_line_break_is_joined() -> None:
    assert clean_text("an inter-\nnational standard") == "an international standard"


def test_hyphen_kept_before_capital() -> None:
    assert clean_text("Python-\nBased tools") == "Python-Based tools"


def test_whitespace_is_normalized() -> None:
    raw = "  one   two\t three  \r\n\r\n\r\n\r\nfour\u00a0five  "
    assert clean_text(raw) == "one two three\n\nfour five"


def test_line_structure_is_kept() -> None:
    assert clean_text("- item one\n- item two") == "- item one\n- item two"


def _doc_with_running_lines(n_pages: int) -> list[Page]:
    return [
        Page(
            number=i,
            text=f"Operating Systems, Lecture 5\nUnique content {i}\nPage {i} of {n_pages}",
        )
        for i in range(1, n_pages + 1)
    ]


def test_find_repeated_signatures_masks_page_counters_only() -> None:
    sigs = find_repeated_signatures(_doc_with_running_lines(8))
    assert "operating systems, lecture 5" in sigs
    assert "<pg>" in sigs
    assert not any("unique" in s for s in sigs)


@pytest.mark.parametrize(
    "footer",
    ["Page {n} of 8", "Page {n} sur 8", "{n}", "- {n} -", "{n} / 8", "Slide {n}", "OS | {n}"],
)
def test_page_counter_styles_are_removed(footer: str) -> None:
    pages = [
        Page(number=i, text=f"Topic {name}\nBody text {name}\n{footer.format(n=i)}")
        for i, name in enumerate(["a", "b", "c", "d", "e", "f", "g", "h"], start=1)
    ]
    cleaned = strip_repeated_lines(pages)
    assert cleaned[2].text == "Topic c\nBody text c"


def test_numbered_body_lines_are_not_mistaken_for_counters() -> None:
    pages = [Page(number=i, text=f"Step {i}\nsome unique words {i}") for i in range(1, 9)]
    assert strip_repeated_lines(pages) == pages


def test_strip_repeated_lines_removes_header_and_footer_only() -> None:
    pages = strip_repeated_lines(_doc_with_running_lines(8))
    assert [p.text for p in pages][:2] == ["Unique content 1", "Unique content 2"]
    assert [p.number for p in pages] == list(range(1, 9))


def test_short_documents_are_left_alone() -> None:
    pages = _doc_with_running_lines(2)
    assert strip_repeated_lines(pages) == pages


def test_clean_document_drops_empty_pages_but_keeps_numbers() -> None:
    doc = Document(
        source="notes.pdf",
        pages=[
            Page(number=1, text="first page"),
            Page(number=2, text="  \n "),
            Page(number=3, text="third page"),
        ],
    )
    cleaned = clean_document(doc)
    assert [p.number for p in cleaned.pages] == [1, 3]
