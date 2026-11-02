# Evaluation question set

`eval/questions.jsonl` is the set of questions VectorNote is measured against: does the right
page come back (retrieval), is the answer faithful and cited, and does it refuse when the notes
do not cover the question. The numbers in the README come from running it, so it has to
describe what you really ask. Write it yourself; a tool can only draft it.

## Workflow

```bash
uv run vectornote ingest                      # your real course files
uv run vectornote eval scaffold -n 40         # drafts at real pages -> eval/draft.jsonl
# edit the file by hand (see below), save it as eval/questions.jsonl
uv run vectornote eval check                  # errors and advice
```

`scaffold` spreads the drafts over your files and pages, so every `expected` page is correct.
`--suggest` lets the local model propose a question and answer for each page. Those drafts are
marked `needs_review` and `check` fails until you have read each one and removed the mark.

## One line per question

```json
{"id": "q007", "question": "Which page replacement policy can get worse with more frames?",
 "type": "factual", "language": "en",
 "expected": [{"source": "os-lecture.pdf", "page": 6}],
 "reference_answer": "FIFO, because of Belady's anomaly.",
 "keywords": ["FIFO", "Belady"]}
```

| Field | Meaning |
|---|---|
| `id` | Unique, for example `q007` |
| `question` | What you would type |
| `type` | `factual`, `definition`, `comparison`, `procedure` or `unanswerable` |
| `language` | `en` or `fr` |
| `expected` | Every page that answers it (any one counts as a hit). Empty only for `unanswerable` |
| `reference_answer` | One or two sentences. Empty only for `unanswerable` |
| `keywords` | Optional terms a correct answer should contain |
| `history` | Optional earlier messages, which makes it a follow-up (tests query rewriting) |

## Writing good questions

- **Aim for 30 to 50.** Fewer than 30 and one question moves the numbers too much.
- **Ask like a student, in your own words.** A question copied from the slide ("the four
  conditions required for a deadlock to occur") is found by any search, so it flatters the
  results. `check` warns when a question repeats six or more words of the passage.
- **Mix types and files**, and include French if you study in French. No file should supply
  more than half of the questions.
- **Add 5 or more unanswerable questions** (about 10 to 15%): things your notes really do not
  cover. They are what lets Phase 4 tune `VECTORNOTE_MIN_RELEVANCE`.
- **Add 3 to 5 follow-ups** with a `history`, written as `"What does the third one mean?"`
  after a conversation that makes "the third one" clear.
- **List every page that answers it.** If the answer is on two pages, list both.

## Copyright

Questions and short reference answers are yours to publish. Do not paste lecture text into
the file: `scaffold` writes a `passage` field to help you write the question, and `check`
asks you to delete it before you commit. `eval/draft*.jsonl` is git-ignored.

## Example

`eval/example/` holds a tiny public corpus (`os-lecture.pdf`, `reseaux.md`) and 15 sample
questions, so you can try the whole workflow without your own files:

```bash
VECTORNOTE_DATA_DIR=eval/example/corpus VECTORNOTE_CHROMA_DIR=/tmp/vn-example \
  uv run vectornote ingest
VECTORNOTE_CHROMA_DIR=/tmp/vn-example uv run vectornote eval check eval/example/questions.example.jsonl
```
