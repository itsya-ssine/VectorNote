"""Clean extracted text: ligatures, hyphenation, whitespace, repeated headers/footers."""

from __future__ import annotations

import math
import re
from collections import Counter

from vectornote.models import Document, Page

# Only the first and last lines of a page can be a header or footer.
EDGE_LINES = 3
# Repeat detection needs enough pages to be meaningful.
MIN_PAGES_FOR_REPEAT_DETECTION = 3
# A line is a header/footer if it appears at the page edges of at least this share of pages.
REPEAT_RATIO = 0.5

_TRANSLATE = str.maketrans(
    {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\u00a0": " ",
        "\u00ad": None,  # soft hyphen
        "\x00": None,
    }
)
_SPACES = re.compile(r"[ \t\u2000-\u200b\u202f\u3000]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(r"([^\W\d_])-\n([^\W\d_])")


def _join_hyphenated(match: re.Match[str]) -> str:
    left, right = match.group(1), match.group(2)
    # "inter-\nnational" -> "international", but keep "Python-\nBased" -> "Python-Based".
    return left + right if right.islower() else f"{left}-{right}"


def clean_text(text: str) -> str:
    """Normalize the text of one page.

    Fixes ligatures, soft hyphens, odd spaces and words hyphenated across line breaks.
    Line structure is kept, because slides and code rely on it.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad\n", "")
    text = text.translate(_TRANSLATE)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _HYPHEN_BREAK.sub(_join_hyphenated, text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


# Page counters: "Page 3 of 40", "Page 3 sur 40", "Slide 3", "3", "- 3 -", "3 / 40",
# and counters glued to a running title ("Operating Systems | 3").
_PAGE_COUNTER = re.compile(
    r"\b(?:page|p\.|slide|diapositive|folio)\s*\d+(?:\s*(?:of|sur|/)\s*\d+)?"
    r"|^[-\u2013\u2014\s]*\d+(?:\s*(?:of|sur|/)\s*\d+)?[-\u2013\u2014\s]*$"
    r"|(?<=[|\u00b7\u2022\-\u2013\u2014])\s*\d+\s*$"
    r"|^\s*\d+\s*(?=[|\u00b7\u2022\-\u2013\u2014])"
)


def _signature(line: str) -> str:
    """Line identity for repeat detection.

    Page counters are masked so 'Page 3 of 40' and 'Page 4 of 40' compare equal.
    Other digits are kept, so body lines such as 'Step 1' and 'Step 2' stay distinct.
    """
    normalized = " ".join(line.lower().split())
    return _PAGE_COUNTER.sub("<pg>", normalized)


def _edge_indices(lines: list[str]) -> list[int]:
    non_empty = [i for i, line in enumerate(lines) if line.strip()]
    return sorted(set(non_empty[:EDGE_LINES] + non_empty[-EDGE_LINES:]))


def find_repeated_signatures(pages: list[Page]) -> set[str]:
    """Return signatures of lines that repeat at the edges of many pages."""
    if len(pages) < MIN_PAGES_FOR_REPEAT_DETECTION:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        lines = page.text.split("\n")
        counts.update({_signature(lines[i]) for i in _edge_indices(lines)})
    threshold = max(MIN_PAGES_FOR_REPEAT_DETECTION, math.ceil(len(pages) * REPEAT_RATIO))
    return {signature for signature, count in counts.items() if count >= threshold}


def strip_repeated_lines(pages: list[Page]) -> list[Page]:
    """Remove running headers, footers and page numbers."""
    repeated = find_repeated_signatures(pages)
    if not repeated:
        return pages
    result: list[Page] = []
    for page in pages:
        lines = page.text.split("\n")
        drop = {i for i in _edge_indices(lines) if _signature(lines[i]) in repeated}
        kept = [line for i, line in enumerate(lines) if i not in drop]
        text = _BLANK_LINES.sub("\n\n", "\n".join(kept)).strip()
        result.append(Page(number=page.number, text=text))
    return result


def clean_document(doc: Document) -> Document:
    """Clean every page, strip running headers/footers and drop empty pages.

    Page numbers are preserved, so citations still match the original file.
    """
    cleaned = [Page(number=p.number, text=clean_text(p.text)) for p in doc.pages]
    stripped = strip_repeated_lines(cleaned)
    return Document(source=doc.source, pages=[p for p in stripped if p.text])
