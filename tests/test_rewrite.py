from __future__ import annotations

import pytest

from vectornote.generation.rewrite import (
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_CHARS,
    REWRITE_SYSTEM_PROMPT,
    build_rewrite_messages,
    clean_rewrite,
    trim_history,
)
from vectornote.models import ChatTurn


def _turn(role: str, content: str) -> ChatTurn:
    return ChatTurn(role="user" if role == "user" else "assistant", content=content)


def test_trim_history_keeps_only_the_latest_messages() -> None:
    history = [_turn("user", f"question {i}") for i in range(10)]
    trimmed = trim_history(history)
    assert len(trimmed) == MAX_HISTORY_MESSAGES
    assert trimmed[-1].content == "question 9"
    assert trimmed[0].content == "question 4"


def test_trim_history_removes_citation_markers_and_extra_whitespace() -> None:
    trimmed = trim_history([_turn("assistant", "A mutex locks [1]. Semaphores\n  count [2, 3].")])
    assert trimmed[0].content == "A mutex locks. Semaphores count."


def test_trim_history_cuts_long_messages_and_drops_empty_ones() -> None:
    trimmed = trim_history([_turn("assistant", "x" * 5000), _turn("user", "  [1]  ")])
    assert len(trimmed) == 1
    assert len(trimmed[0].content) == MAX_MESSAGE_CHARS + 3
    assert trimmed[0].content.endswith("...")


def test_rewrite_messages_show_the_conversation_then_the_follow_up() -> None:
    history = [
        _turn("user", "What is a mutex?"),
        _turn("assistant", "A mutex gives mutual exclusion [1]."),
    ]
    system, user = build_rewrite_messages(history, "  explain that more ")
    assert system == {"role": "system", "content": REWRITE_SYSTEM_PROMPT}
    body = user["content"]
    assert body.index("User: What is a mutex?") < body.index("Assistant: A mutex gives mutual")
    assert "[1]" not in body
    assert body.endswith("Follow-up question: explain that more\n\nStandalone question:")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("How does a mutex work?", "How does a mutex work?"),
        ("Standalone question: What is a semaphore?", "What is a semaphore?"),
        ('"What is a semaphore?"', "What is a semaphore?"),
        ("« Qu'est-ce qu'un sémaphore ? »", "Qu'est-ce qu'un sémaphore ?"),
        ("What is a semaphore?\n\nA semaphore is a counter...", "What is a semaphore?"),
        ("\n\n  What is a semaphore?  \n", "What is a semaphore?"),
    ],
)
def test_clean_rewrite_accepts_a_question(raw: str, expected: str) -> None:
    assert clean_rewrite(raw, "and that one?") == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   \n", "NOT_FOUND", "x" * 400],
)
def test_clean_rewrite_falls_back_to_the_original(raw: str) -> None:
    assert clean_rewrite(raw, "and that one?") == "and that one?"
