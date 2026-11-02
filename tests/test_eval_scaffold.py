from __future__ import annotations

import json
from collections import Counter
from collections.abc import Generator, Mapping, Sequence

from vectornote.evaluation.dataset import check_questions
from vectornote.evaluation.scaffold import (
    MIN_PASSAGE_CHARS,
    PASSAGE_PREVIEW_CHARS,
    PLACEHOLDER,
    SUGGEST_SYSTEM_PROMPT,
    draft_questions,
    sample_chunks,
    suggest_question,
)
from vectornote.models import Chunk


def _chunk(source: str, page: int, index: int = 0, text: str | None = None) -> Chunk:
    body = text if text is not None else ("Some course text about threads. " * 12)
    return Chunk(chunk_id=f"{source}#p{page}-c{index}", source=source, page=page, text=body)


def _corpus() -> list[Chunk]:
    chunks = [_chunk("os.pdf", page) for page in range(1, 21)]
    chunks += [_chunk("os.pdf", 5, index=1)]  # a second chunk on page 5
    chunks += [_chunk("net.pdf", page) for page in range(1, 7)]
    chunks += [_chunk("tiny.md", 1, text="Title")]
    return chunks


class StubLLM:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.messages: list[list[dict[str, str]]] = []
        self.max_tokens: list[int | None] = []

    def complete(
        self, messages: Sequence[Mapping[str, str]], max_tokens: int | None = None
    ) -> str:
        self.messages.append([dict(m) for m in messages])
        self.max_tokens.append(max_tokens)
        return self.replies.pop(0)

    def stream(self, messages: Sequence[Mapping[str, str]]) -> Generator[str, None, None]:
        yield self.complete(messages)


# ---- sampling ---------------------------------------------------------------


def test_sampling_is_deterministic_and_seeded() -> None:
    first = sample_chunks(_corpus(), 10, seed=1)
    assert first == sample_chunks(_corpus(), 10, seed=1)
    assert first != sample_chunks(_corpus(), 10, seed=2)


def test_sampling_gives_every_file_a_turn_and_skips_tiny_chunks() -> None:
    picked = sample_chunks(_corpus(), 8)
    counts = Counter(c.source for c in picked)
    assert counts == {"os.pdf": 4, "net.pdf": 4}
    assert all(len(c.text) >= MIN_PASSAGE_CHARS for c in picked)


def test_each_page_is_used_once_before_any_page_repeats() -> None:
    picked = sample_chunks(_corpus(), 26)  # exactly the number of distinct pages
    pages = [(c.source, c.page) for c in picked]
    assert len(set(pages)) == len(pages) == 26


def test_asking_for_more_than_the_pages_reuses_pages_and_stops_at_the_supply() -> None:
    assert len(sample_chunks(_corpus(), 27)) == 27
    assert len(sample_chunks(_corpus(), 500)) == 27  # all eligible chunks, no more
    assert sample_chunks([], 5) == []


def test_results_come_back_in_reading_order() -> None:
    picked = sample_chunks(_corpus(), 12)
    keys = [(c.source, c.page, c.chunk_id) for c in picked]
    assert keys == sorted(keys)


# ---- drafts -----------------------------------------------------------------


def test_drafts_without_a_model_are_placeholders_at_the_right_pages() -> None:
    chunks = sample_chunks(_corpus(), 3)
    drafts = draft_questions(chunks)
    assert [d.id for d in drafts] == ["q001", "q002", "q003"]
    for draft, chunk in zip(drafts, chunks, strict=True):
        assert draft.question == PLACEHOLDER
        assert [(e.source, e.page) for e in draft.expected] == [(chunk.source, chunk.page)]
        assert draft.passage == chunk.text[:PASSAGE_PREVIEW_CHARS]
        assert not draft.needs_review


def test_the_language_is_guessed_from_the_passage() -> None:
    french = _chunk("r.md", 1, text="Le client envoie un segment SYN et le serveur répond par un "
                    "segment SYN-ACK, puis le client confirme avec un ACK. Les données sont "
                    "ensuite échangées dans les deux sens, et la connexion est établie. " * 2)
    english = _chunk("o.pdf", 1)
    drafts = draft_questions([english, french])
    assert [d.language for d in drafts] == ["en", "fr"]


def test_drafts_are_flagged_by_the_checker_until_they_are_edited() -> None:
    drafts = draft_questions(sample_chunks(_corpus(), 4))
    report = check_questions(drafts, {"os.pdf": set(range(1, 21)), "net.pdf": set(range(1, 7))})
    assert sum("placeholder" in e for e in report.errors) == 4
    assert any("`passage`" in w for w in report.warnings)


# ---- model suggestions ------------------------------------------------------


def test_suggest_question_parses_the_json_reply() -> None:
    llm = StubLLM(['Sure! {"question": " What is a mutex? ", "answer": "A lock."}'])
    assert suggest_question(llm, "passage text") == ("What is a mutex?", "A lock.")
    system, user = llm.messages[0]
    assert system == {"role": "system", "content": SUGGEST_SYSTEM_PROMPT}
    assert user == {"role": "user", "content": "passage text"}
    assert llm.max_tokens == [300]


def test_unusable_replies_give_none() -> None:
    for reply in ["no json here", "{broken", '{"question": "only a question"}',
                  '{"question": "", "answer": "x"}', '{"question": 3, "answer": "x"}']:
        assert suggest_question(StubLLM([reply]), "p") is None


def test_suggested_drafts_need_review_and_failed_ones_stay_placeholders() -> None:
    llm = StubLLM([json.dumps({"question": "Why lock?", "answer": "To protect data."}), "garbage"])
    drafts = draft_questions(sample_chunks(_corpus(), 2), llm)
    assert drafts[0].question == "Why lock?"
    assert drafts[0].reference_answer == "To protect data."
    assert drafts[0].needs_review
    assert drafts[1].question == PLACEHOLDER
    assert not drafts[1].needs_review
