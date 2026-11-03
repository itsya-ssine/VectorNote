Measured on 46 questions with `sentence-transformers/all-MiniLM-L6-v2`, chunks of 800 characters (100 overlap), top 5.

**Retrieval**

| mode | hit@1 | hit@3 | hit@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| vector | 63% | 91% | 97% | 0.77 | 13.1 | 17.0 |
| bm25 | 66% | 91% | 97% | 0.78 | 0.7 | 1.2 |
| hybrid | 77% | 100% | 100% | 0.87 | 18.5 | 22.3 |

35 answerable, 7 unanswerable; 4 follow-up(s) skipped, use --rewrite to include them.

**Relevance threshold (hybrid)**

| threshold | answerable kept | unanswerable refused |
|---|---|---|
| 0.15 | 100% | 0% |
| 0.20 | 100% | 14% |
| 0.25 | 100% | 14% |
| 0.30 | 100% | 14% |
| 0.35 (current) | 100% | 29% |
| 0.40 | 94% | 57% |
| 0.45 | 89% | 86% |
| 0.50 | 69% | 86% |
