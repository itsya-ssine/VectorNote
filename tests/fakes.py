"""Test doubles shared by several test modules."""

from __future__ import annotations

import re
import time
from collections.abc import Generator, Mapping, Sequence

from vectornote.generation import OllamaError


class FakeLLM:
    """Records the conversations it receives and replies with a canned answer.

    `error` makes every call fail; `fail_after` lets streaming fail midway.
    """

    def __init__(self, reply: str = "A mutex gives mutual exclusion [1].") -> None:
        self.reply = reply
        self.error: Exception | None = None
        self.fail_after: int | None = None
        self.calls: list[list[dict[str, str]]] = []
        self.stream_closed = False
        self.delay = 0.0  # seconds between streamed pieces
        self.pieces_sent = 0
        self.used: list[str] = []

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        self.used.append("complete")
        self.calls.append([dict(m) for m in messages])
        if self.error:
            raise self.error
        return self.reply

    def stream(self, messages: Sequence[Mapping[str, str]]) -> Generator[str, None, None]:
        self.used.append("stream")
        self.calls.append([dict(m) for m in messages])
        self.stream_closed = False
        self.pieces_sent = 0
        if self.error:
            raise self.error
        try:
            for index, word in enumerate(re.findall(r"\S+\s*", self.reply)):
                if self.fail_after is not None and index >= self.fail_after:
                    raise OllamaError("Ollama stopped the reply: model crashed")
                time.sleep(self.delay)
                self.pieces_sent += 1
                yield word
        finally:
            self.stream_closed = True
