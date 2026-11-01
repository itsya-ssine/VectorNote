"""Prompt construction and canned replies."""

from __future__ import annotations

import re
from typing import Literal

from vectornote.models import SearchResult

NOT_FOUND = "NOT_FOUND"

# Context passages beyond this many characters are dropped (lowest ranked first).
MAX_CONTEXT_CHARS = 6000

SYSTEM_PROMPT = (
    "You are VectorNote, a study assistant. Answer the question using ONLY the numbered "
    "context passages in the user message.\n\n"
    "Rules:\n"
    "- After each claim, cite the passage it comes from with its number in square "
    "brackets, like [1] or [2][3].\n"
    f"- If the passages do not contain the answer, reply with exactly: {NOT_FOUND}\n"
    "- Never use outside knowledge and never invent citations or facts.\n"
    "- Answer in the same language as the question. Be concise."
)

Refusal = Literal["not_found", "empty_index"]

_FRENCH_MARKERS = frozenset(
    "le la les des du un une est sont quel quelle quels comment pourquoi que qu quoi "
    "différence entre et pour dans avec peut expliquer".split()
)
_WORD = re.compile(r"\w+")

_MESSAGES: dict[tuple[str, Refusal], str] = {
    ("en", "not_found"): "I couldn't find the answer to that in your documents.",
    ("fr", "not_found"): "Je n'ai pas trouvé la réponse dans vos documents.",
    ("en", "empty_index"): "Your index is empty. Add documents first (`vectornote ingest`).",
    ("fr", "empty_index"): (
        "Votre index est vide. Ajoutez d'abord des documents (`vectornote ingest`)."
    ),
}


def _language(question: str) -> str:
    words = {w.lower() for w in _WORD.findall(question)}
    return "fr" if len(words & _FRENCH_MARKERS) >= 2 else "en"


def refusal_message(question: str, reason: Refusal = "not_found") -> str:
    """Fixed reply used when no model call is needed (or the model found nothing)."""
    return _MESSAGES[(_language(question), reason)]


def select_context(
    results: list[SearchResult], max_chars: int = MAX_CONTEXT_CHARS
) -> list[SearchResult]:
    """Keep the best-ranked passages that fit the character budget (always at least one)."""
    kept: list[SearchResult] = []
    used = 0
    for result in results:
        size = len(result.chunk.text)
        if kept and used + size > max_chars:
            break
        kept.append(result)
        used += size
    return kept


def build_messages(question: str, context: list[SearchResult]) -> list[dict[str, str]]:
    """Chat messages: the rules, then numbered passages and the question."""
    blocks = [
        f"[{number}] {result.chunk.source}, page {result.chunk.page}\n{result.chunk.text}"
        for number, result in enumerate(context, start=1)
    ]
    user = "Context passages:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question.strip()}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
