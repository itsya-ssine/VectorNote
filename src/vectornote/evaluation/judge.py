"""A rough faithfulness check: does the answer only say what its passages say?

A small local model is a weak judge, so treat the result as a signal to investigate, not as
a score to quote on its own. `eval run --output` saves every answer with its sources so the
doubtful ones can be read by hand.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from vectornote.generation import ChatModel
from vectornote.models import SearchResult

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
JUDGE_MAX_TOKENS = 8

JUDGE_SYSTEM_PROMPT = (
    "You check an answer against the source passages it was written from.\n"
    f"Reply with exactly {SUPPORTED} if every claim in the answer is stated in the passages.\n"
    f"Reply with exactly {UNSUPPORTED} if the answer contains anything the passages do not say.\n"
    "Ignore the [1] style citation markers and ignore how the answer is worded. "
    "Reply with that one word and nothing else."
)

_VERDICT = re.compile(r"[A-Za-z_]+")


def build_judge_messages(answer: str, context: Sequence[SearchResult]) -> list[dict[str, str]]:
    """The judge conversation: numbered passages, then the answer to check."""
    blocks = [
        f"[{number}] {result.chunk.text}" for number, result in enumerate(context, start=1)
    ]
    user = "Passages:\n\n" + "\n\n".join(blocks) + f"\n\nAnswer to check:\n{answer.strip()}"
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_verdict(reply: str) -> bool | None:
    """True for SUPPORTED, False for UNSUPPORTED, None when the reply is neither."""
    match = _VERDICT.search(reply)
    if match is None:
        return None
    word = match.group(0).upper()
    if word == SUPPORTED:
        return True
    if word == UNSUPPORTED:
        return False
    return None


def judge_faithfulness(
    llm: ChatModel, answer: str, context: Sequence[SearchResult]
) -> bool | None:
    """Ask the model whether the answer is supported by the passages it was given."""
    reply = llm.complete(build_judge_messages(answer, context), max_tokens=JUDGE_MAX_TOKENS)
    return parse_verdict(reply)
