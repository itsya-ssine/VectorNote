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

## The committed question set

`eval/questions.jsonl` has 46 questions about the free textbook *Python Programming* by
Hans-Petter Halvorsen (ISBN 978-82-691106-4-7; the author's page is
https://www.halvorsen.blog/documents/programming/python/). The book is not in this repository:
save your copy as `data/Python_Programming.pdf` (the file name is part of every `expected`
entry) and run `vectornote ingest`.

| | |
|---|---|
| Answerable | 35, spread over all chapters: setup, editors, variables, plotting, loops, functions, classes, modules, files, errors, pip and conda, environments, math and statistics |
| Follow-ups | 4, each with a `history` (the question only makes sense after the conversation) |
| Unanswerable | 7: six Python topics the book never covers (dictionaries, lambda, inheritance, unit testing, tuples, JSON) and one off-topic question |

Things worth knowing when you read the numbers:

- **Pages are PDF pages**, which is what VectorNote cites. The book's printed page numbers are
  3 lower (printed page 12 is PDF page 15).
- **Every page that answers a question is listed**, because the book repeats material (for
  example radians and degrees on pages 67, 77 and 129-130), so a hit on any of them counts.
- **The questions were drafted from the book's text** and every `expected` page was checked
  against the indexed text. They are written in plain words rather than the book's wording, but
  they are not questions you asked while studying. A set from your own study sessions is a
  harder and more honest test; replace or extend this one when you have it.
- **All questions come from one file and are in English**, so the one-file-share check does not
  apply and the French path is not exercised by this set (the public example in `eval/example/`
  does).

## Measure it

Once `eval check` has no errors:

```bash
uv run vectornote eval run                    # retrieval: vector, bm25 and hybrid, offline
uv run vectornote eval run --answers --judge  # also answers, citations, refusals (needs Ollama)
uv run vectornote eval run --format markdown  # README-ready tables on stdout
uv run vectornote eval run -o eval/results.json   # everything, with every answer (git-ignored)
```

| Number | Meaning |
|---|---|
| hit@k | Share of answerable questions with an expected page among the top k results |
| MRR | Mean of `1 / rank` of the first expected page (1.0 means always first) |
| p50 / p95 ms | Typical and slow search time, measured after a warm-up search |
| answered / refused correctly | Does it answer what the notes cover, and refuse what they do not |
| citation on an expected page | The answer cites a passage from a page you listed in `expected` |
| keyword coverage | Share of your `keywords` that appear in the answer |
| faithfulness | A model's yes/no on whether the answer only says what its passages say (rough) |

Follow-up questions need the model to be rewritten, so retrieval skips them unless you add
`--rewrite`; `--answers` always includes them.

### Tuning the relevance threshold

The "Relevance threshold" table shows, for each minimum cosine similarity, how many answerable
questions would still find a passage ("kept") and how many unanswerable ones would be refused.
Pick the value that refuses most unanswerable questions while keeping nearly all answerable
ones, then set `VECTORNOTE_MIN_RELEVANCE`. This needs the 5 or more unanswerable questions
that `check` asks for; with none, the "refused" column reads `n/a`.

### Comparing chunk sizes

Indexing skips files it has already seen, so use one index per size:

```bash
for size in 400 800 1200; do
  export VECTORNOTE_CHROMA_DIR=/tmp/vn-$size VECTORNOTE_CHUNK_SIZE=$size \
         VECTORNOTE_CHUNK_OVERLAP=$((size / 8))
  uv run vectornote ingest
  echo "chunk size $size"
  uv run vectornote eval run --format markdown
done
```

Run it on your real files and the real embedding model. On the small public example corpus every
mode finds every page, so its numbers say nothing about quality (and `VECTORNOTE_EMBEDDING_MODEL=hashing`
has no semantics at all).
