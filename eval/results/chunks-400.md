Measured on 46 questions with `sentence-transformers/all-MiniLM-L6-v2`, chunks of 400 characters (50 overlap), top 5.

**Retrieval**

| mode | hit@1 | hit@3 | hit@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| vector | 74% | 94% | 94% | 0.83 | 13.0 | 14.3 |
| bm25 | 63% | 83% | 94% | 0.75 | 0.8 | 1.6 |
| hybrid | 83% | 97% | 100% | 0.90 | 17.6 | 19.4 |

35 answerable, 7 unanswerable; 4 follow-up(s) skipped, use --rewrite to include them.

**Relevance threshold (hybrid)**

| threshold | answerable kept | unanswerable refused |
|---|---|---|
| 0.15 | 100% | 0% |
| 0.20 | 100% | 14% |
| 0.25 | 100% | 14% |
| 0.30 | 100% | 14% |
| 0.35 (current) | 100% | 29% |
| 0.40 | 100% | 57% |
| 0.45 | 94% | 57% |
| 0.50 | 86% | 86% |
