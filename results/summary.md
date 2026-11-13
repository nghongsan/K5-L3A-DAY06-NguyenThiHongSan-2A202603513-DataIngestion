# Results summary

Model `intfloat/multilingual-e5-small` (384d, local sentence-transformers on cpu, cost $0); store chromadb 1.5.9 PersistentClient, HNSW, cosine; run at 2026-11-13T09:59:58+00:00.

| Strategy | Split | Hit@1 | Evidence Hit@3 | Page Hit@3 | Evidence split | Filter compliant | ANN = exact top-3 | Chunks | Embed s | ms/query | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | dev | 13/19 | 18/19 | 19/19 | 0 | 1/3 | 19/19 | 210 | 4.13 | 20.3 | $0 |
| A | test | 3/6 | 4/6 | 6/6 | 1 | 2/2 | 6/6 | 210 | 4.13 | 23.0 | $0 |
| B | dev | 16/19 | 18/19 | 19/19 | 0 | 1/3 | 19/19 | 263 | 3.34 | 21.3 | $0 |
| B | test | 5/6 | 5/6 | 5/6 | 0 | 2/2 | 6/6 | 263 | 3.34 | 23.9 | $0 |
| C | dev | 17/19 | 18/19 | 19/19 | 0 | 3/3 | 19/19 | 263 | 0.0 | 21.0 | $0 |
| C | test | 5/6 | 5/6 | 5/6 | 0 | 2/2 | 6/6 | 263 | 0.0 | 23.5 | $0 |

| Strategy | Coherence mean /2 (n) | Metadata complete & correct (test top-3) | Filter compliant (test) | Grounding 0/1/2 | Grounding mean /2 |
|---|---|---|---|---|---|
| A | 0.80 (10) | 18/18 | 2/2 questions | 0/1/5 | 1.83 |
| B | 1.50 (10) | 18/18 | 2/2 questions | 0/1/5 | 1.83 |
| C | 1.50 (10) | 18/18 | 2/2 questions | 0/1/5 | 1.83 |

Chunk length statistics (characters):

| Strategy | chunks | total chars | total tokens (e5 tokenizer) | max tokens | >512 tokens | min | p10 | median | mean | p90 | max |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 210 | 87260 | 26010 | 220 | 0 | 51 | 189 | 499.0 | 415.5 | 500 | 500 |
| B | 263 | 80459 | 24209 | 211 | 0 | 66 | 205 | 266 | 305.9 | 476 | 742 |
| C | 263 | 80459 | 24209 | 211 | 0 | 66 | 205 | 266 | 305.9 | 476 | 742 |

Re-ingest: same version rewrote 0 chunks (no duplicates: True); changed page 170 removed 3 stale chunks (ok: True). Model load 7.86 s, PDF read 0.61 s.
