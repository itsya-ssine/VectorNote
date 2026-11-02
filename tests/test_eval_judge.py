from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence

import pytest

from vectornote.evaluation.judge import (
    JUDGE_MAX_TOKENS,
    JUDGE_SYSTEM_PROMPT,
    build_judge_messages,
    judge_faithfulness,
    parse_verdict,
)
from vectornote.models import Chunk, SearchResult


def _context() -> list[SearchResult]:
    chunks = [
        Chunk(chunk_id="a", text="A mutex has an owner.", source="os.pdf", page=2),
        Chunk(chunk_id="b", text="A semaphore is a counter.", source="os.pdf", page=3),
    ]
    return [SearchResult(chunk=c, score=1.0) for c in chunks]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("SUPPORTED", True),
        ("supported.", True),
        ("  Supported\n", True),
        ("UNSUPPORTED", False),
        ("unsupported: the answer adds a claim", False),
        ('"UNSUPPORTED"', False),
        ("The answer looks fine", None),
        ("", None),
        ("123", None),
    ],
)
def test_parse_verdict(reply: str, expected: bool | None) -> None:
    assert parse_verdict(reply) is expected


def test_judge_prompt_numbers_the_passages_and_ends_with_the_answer() -> None:
    messages = build_judge_messages("A mutex has an owner [1].", _context())
    assert messages[0] == {"role": "system", "content": JUDGE_SYSTEM_PROMPT}
    user = messages[1]["content"]
    assert "[1] A mutex has an owner." in user
    assert "[2] A semaphore is a counter." in user
    assert user.endswith("Answer to check:\nA mutex has an owner [1].")


class _Recorder:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.max_tokens: list[int | None] = []

    def complete(
        self, messages: Sequence[Mapping[str, str]], max_tokens: int | None = None
    ) -> str:
        self.max_tokens.append(max_tokens)
        return self.reply

    def stream(self, messages: Sequence[Mapping[str, str]]) -> Generator[str, None, None]:
        yield self.reply


def test_judge_faithfulness_asks_for_a_short_verdict() -> None:
    llm = _Recorder("SUPPORTED")
    assert judge_faithfulness(llm, "A mutex has an owner [1].", _context()) is True
    assert llm.max_tokens == [JUDGE_MAX_TOKENS]
    assert judge_faithfulness(_Recorder("UNSUPPORTED"), "x", _context()) is False
    assert judge_faithfulness(_Recorder("hmm"), "x", _context()) is None
