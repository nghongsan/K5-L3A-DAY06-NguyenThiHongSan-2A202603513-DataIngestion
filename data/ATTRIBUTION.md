# Attribution & license of the corpus

Text in `results/pages.jsonl`, `results/chunks_*.jsonl`, `results/traces_*.jsonl`, `results/audit/*.csv` and the
evidence quotes in `benchmark/` are excerpts of:

**Introduction to Python Programming** by Udayan Das, Aubrey Lawson, Chris Mayfield and Narges Norouzi, OpenStax
(Rice University). Source: https://openstax.org/details/books/introduction-python-programming
License: **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International** (https://creativecommons.org/licenses/by-nc-sa/4.0/).

Changes made: extracted chapters 4–6 (PDF pages 95–174) with pypdf; removed page footers, multimedia links and
"TRY IT" labels; Unicode/whitespace normalization; split into chunks. Used for non-commercial coursework only.
These derived excerpts are shared under the same CC BY-NC-SA 4.0 license. The original PDF is not redistributed
in this repo (see `scripts/download_corpus.sh`).
