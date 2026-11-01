"""Read the `[n]` citation markers out of a model answer."""

from __future__ import annotations

import re

from vectornote.generation.prompts import NOT_FOUND

_MARKER = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def extract_citations(answer: str, passage_count: int) -> list[int]:
    """Passage numbers the answer cites, in order of first use.

    Numbers outside 1..passage_count (invented citations) are ignored.
    """
    cited: list[int] = []
    for marker in _MARKER.finditer(answer):
        for raw in re.split(r"[,;]", marker.group(1)):
            number = int(raw)
            if 1 <= number <= passage_count and number not in cited:
                cited.append(number)
    return cited


def is_not_found(answer: str) -> bool:
    """True when the model reported that the context lacks the answer."""
    return answer.strip().upper().startswith(NOT_FOUND)
