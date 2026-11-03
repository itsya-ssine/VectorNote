Measured on 46 questions with `sentence-transformers/all-MiniLM-L6-v2`, chunks of 1200 characters (150 overlap), top 5.

**Retrieval**

| mode | hit@1 | hit@3 | hit@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| vector | 60% | 89% | 91% | 0.75 | 13.8 | 14.9 |
| bm25 | 66% | 86% | 94% | 0.77 | 0.8 | 1.1 |
| hybrid | 74% | 97% | 100% | 0.86 | 17.5 | 21.1 |

35 answerable, 7 unanswerable; 4 follow-up(s) skipped, use --rewrite to include them.

**Relevance threshold (hybrid)**

| threshold | answerable kept | unanswerable refused |
|---|---|---|
| 0.15 | 100% | 0% |
| 0.20 | 100% | 14% |
| 0.25 | 100% | 14% |
| 0.30 | 100% | 14% |
| 0.35 (current) | 97% | 43% |
| 0.40 | 94% | 43% |
| 0.45 | 89% | 86% |
| 0.50 | 66% | 86% |
