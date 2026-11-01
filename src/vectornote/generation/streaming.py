"""Helpers for token streams: hide reasoning blocks and the NOT_FOUND marker."""

from __future__ import annotations

from vectornote.generation.prompts import NOT_FOUND

_OPEN = "<think>"
_CLOSE = "</think>"


def _partial_suffix(text: str, marker: str) -> int:
    """Length of the longest suffix of `text` that is a proper prefix of `marker`."""
    for size in range(min(len(text), len(marker) - 1), 0, -1):
        if text.endswith(marker[:size]):
            return size
    return 0


class ThinkFilter:
    """Removes `<think>...</think>` blocks from a stream, even when a tag is split across chunks."""

    def __init__(self) -> None:
        self._pending = ""
        self._inside = False
        self._skip_newlines = False

    def feed(self, piece: str) -> str:
        self._pending += piece
        out: list[str] = []
        while True:
            if self._inside:
                end = self._pending.find(_CLOSE)
                if end == -1:
                    keep = _partial_suffix(self._pending, _CLOSE)
                    self._pending = self._pending[len(self._pending) - keep:]
                    break
                self._pending = self._pending[end + len(_CLOSE):]
                self._inside = False
                self._skip_newlines = True
                continue
            if self._skip_newlines:
                self._pending = self._pending.lstrip("\r\n")
                if self._pending:
                    self._skip_newlines = False
            start = self._pending.find(_OPEN)
            if start == -1:
                hold = _partial_suffix(self._pending, _OPEN)
                cut = len(self._pending) - hold
                out.append(self._pending[:cut])
                self._pending = self._pending[cut:]
                break
            out.append(self._pending[:start])
            self._pending = self._pending[start + len(_OPEN):]
            self._inside = True
        return "".join(out)

    def finish(self) -> str:
        """Flush what was held back (text that merely looked like the start of a tag)."""
        rest = "" if self._inside else self._pending
        self._pending = ""
        return rest


class NotFoundGate:
    """Holds back the start of a reply until it is clear it is not the NOT_FOUND marker.

    Without it, the raw marker would flash on screen before the reply is recognized as
    "the documents do not contain the answer". Leading whitespace is dropped.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._decided = False
        self._suppress = False

    def feed(self, piece: str) -> str:
        if self._decided:
            return "" if self._suppress else piece
        self._buffer += piece
        candidate = self._buffer.lstrip().upper()
        if not candidate:
            return ""
        if candidate.startswith(NOT_FOUND):
            self._decided = True
            self._suppress = True
            return ""
        if NOT_FOUND.startswith(candidate):
            return ""  # could still turn into the marker
        self._decided = True
        released, self._buffer = self._buffer.lstrip(), ""
        return released

    def finish(self) -> str:
        """Release whatever is still held when the stream ends."""
        if self._decided:
            return ""
        self._decided = True
        released, self._buffer = self._buffer.lstrip(), ""
        return released
