"""Turn a follow-up question into a standalone one, using the recent conversation."""

from __future__ import annotations

import re
from collections.abc import Sequence

from vectornote.generation.prompts import NOT_FOUND
from vectornote.models import ChatTurn

# Only the latest exchanges matter for resolving "it", "that", "the second one"...
MAX_HISTORY_MESSAGES = 6
MAX_MESSAGE_CHARS = 600
# A rewrite is a short question; anything much longer is the model going off-script.
MAX_REWRITE_CHARS = 300
REWRITE_MAX_TOKENS = 128

REWRITE_SYSTEM_PROMPT = (
    "You rewrite follow-up questions. Given a conversation and a follow-up question, "
    "rewrite the follow-up as one complete, standalone question that can be understood "
    "without the conversation.\n\n"
    "Rules:\n"
    "- Replace pronouns and vague references (it, that, they, the second one, ce, cela, "
    "celui-ci) with what they refer to.\n"
    "- Keep the language of the follow-up question.\n"
    "- If the follow-up is already standalone, return it unchanged.\n"
    "- Output ONLY the question. Do not answer it and do not explain."
)

_CITATION = re.compile(r"\s*\[\d+(?:\s*[,;]\s*\d+)*\]")
_LABEL = re.compile(
    r"^(?:standalone question|rewritten question|question|question autonome)\s*:\s*",
    re.IGNORECASE,
)


def trim_history(history: Sequence[ChatTurn]) -> list[ChatTurn]:
    """Keep the latest messages, drop `[n]` citation markers and cut long messages."""
    trimmed: list[ChatTurn] = []
    for turn in history[-MAX_HISTORY_MESSAGES:]:
        content = " ".join(_CITATION.sub("", turn.content).split())
        if len(content) > MAX_MESSAGE_CHARS:
            content = content[:MAX_MESSAGE_CHARS].rstrip() + "..."
        if content:
            trimmed.append(ChatTurn(role=turn.role, content=content))
    return trimmed


def build_rewrite_messages(history: Sequence[ChatTurn], question: str) -> list[dict[str, str]]:
    lines = [
        f"{'User' if turn.role == 'user' else 'Assistant'}: {turn.content}"
        for turn in trim_history(history)
    ]
    user = (
        "Conversation:\n"
        + "\n".join(lines)
        + f"\n\nFollow-up question: {question.strip()}\n\nStandalone question:"
    )
    return [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def clean_rewrite(raw: str, original: str) -> str:
    """Accept the model's rewrite only if it looks like a question; otherwise keep the original."""
    text = raw.strip()
    if not text or NOT_FOUND in text.upper():
        return original
    line = next((candidate.strip() for candidate in text.splitlines() if candidate.strip()), "")
    line = _LABEL.sub("", line).strip().strip("\"'\u201c\u201d\u00ab\u00bb").strip()
    if not line or len(line) > max(MAX_REWRITE_CHARS, 4 * len(original)):
        return original
    return line
