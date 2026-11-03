Measured on 46 questions with `sentence-transformers/all-MiniLM-L6-v2`, chunks of 800 characters (100 overlap), top 5, answers by `llama3.2:3b` (Ollama), hybrid search, relevance threshold 0.35.

**Answers** (46 questions, follow-ups included)

| metric | result |
|---|---|
| answered (of answerable) | 97% |
| refused correctly (of unanswerable) | 100% |
| answers with citations | 89% |
| citation on an expected page | 79% |
| keyword coverage | 85% |
| faithfulness (model judge) | 79% (38 judged) |
| latency p50 / p95 | 54.2 s / 78.0 s |

The faithfulness judge is the same small local model, so treat that line as a signal to investigate.
