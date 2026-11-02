"""Draft a question file from the indexed documents.

The drafts point at real pages, so every expected page number is correct. Writing the
questions and answers is left to you (or reviewed, if an LLM drafted them), because
questions written from a passage in the passage's own words make retrieval look better
than it is.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from collections.abc import Sequence

from vectornote.evaluation.dataset import EvalQuestion, Evidence
from vectornote.generation import ChatModel
from vectornote.generation.prompts import guess_language
from vectornote.models import Chunk

MIN_PASSAGE_CHARS = 200
PASSAGE_PREVIEW_CHARS = 700
SUGGEST_MAX_TOKENS = 300
PLACEHOLDER = "TODO: write a question that this passage answers"

SUGGEST_SYSTEM_PROMPT = (
    "You write exam questions for students. Given a passage from course notes, write ONE "
    "question a student could ask whose answer is in the passage, and a short answer "
    "(one or two sentences).\n\n"
    "Rules:\n"
    "- Use your own words. Never reuse a phrase of more than three words from the passage.\n"
    "- The question must make sense on its own: never say 'the passage' or 'the text'.\n"
    "- Write in the language of the passage.\n"
    'Reply with JSON only: {"question": "...", "answer": "..."}'
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
# Passages are long, so a few incidental French words must not tip the guess.
_PASSAGE_FRENCH_MARKERS = 4


def sample_chunks(chunks: Sequence[Chunk], count: int, seed: int = 42) -> list[Chunk]:
    """Pick `count` chunks spread over files and pages (same seed, same picks).

    Files take turns, and each page is used once before any page is used twice.
    Very short chunks (titles, captions) are skipped.
    """
    rng = random.Random(seed)
    eligible = sorted(
        (c for c in chunks if len(c.text) >= MIN_PASSAGE_CHARS),
        key=lambda c: (c.source, c.page, c.chunk_id),
    )
    pages: dict[str, dict[int, list[Chunk]]] = defaultdict(lambda: defaultdict(list))
    for chunk in eligible:
        pages[chunk.source][chunk.page].append(chunk)

    queues: dict[str, list[Chunk]] = {}
    for source, by_page in sorted(pages.items()):
        queue = [rng.choice(by_page[page]) for page in sorted(by_page)]
        rng.shuffle(queue)
        queues[source] = queue

    picked: list[Chunk] = []
    while len(picked) < count and any(queues.values()):
        for source in sorted(queues):
            if queues[source] and len(picked) < count:
                picked.append(queues[source].pop())
    if len(picked) < count:  # more questions than pages: reuse pages
        spare = [c for c in eligible if c not in picked]
        rng.shuffle(spare)
        picked.extend(spare[: count - len(picked)])
    return sorted(picked, key=lambda c: (c.source, c.page, c.chunk_id))


def suggest_question(llm: ChatModel, passage: str) -> tuple[str, str] | None:
    """Ask the model for a draft (question, answer); None if its reply is unusable."""
    reply = llm.complete(
        [
            {"role": "system", "content": SUGGEST_SYSTEM_PROMPT},
            {"role": "user", "content": passage},
        ],
        max_tokens=SUGGEST_MAX_TOKENS,
    )
    match = _JSON_OBJECT.search(reply)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    question, answer = data.get("question"), data.get("answer")
    if not isinstance(question, str) or not isinstance(answer, str):
        return None
    question, answer = question.strip(), answer.strip()
    return (question, answer) if question and answer else None


def draft_questions(chunks: Sequence[Chunk], llm: ChatModel | None = None) -> list[EvalQuestion]:
    """One draft per chunk, pointing at the chunk's page.

    Without `llm` the question is a placeholder for you to write. With it, the model
    proposes a question and answer, marked `needs_review` until you have checked them.
    """
    drafts: list[EvalQuestion] = []
    for index, chunk in enumerate(chunks, start=1):
        question, answer, review = PLACEHOLDER, "", False
        if llm is not None:
            suggestion = suggest_question(llm, chunk.text)
            if suggestion is not None:
                question, answer = suggestion
                review = True
        drafts.append(
            EvalQuestion(
                id=f"q{index:03d}",
                question=question,
                language="fr"
                if guess_language(chunk.text, _PASSAGE_FRENCH_MARKERS) == "fr"
                else "en",
                expected=[Evidence(source=chunk.source, page=chunk.page)],
                reference_answer=answer,
                passage=chunk.text[:PASSAGE_PREVIEW_CHARS],
                needs_review=review,
            )
        )
    return drafts
