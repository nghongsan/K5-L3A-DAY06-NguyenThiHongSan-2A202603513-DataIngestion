"""Re-ingest test: same version => no duplicates; changed document => stale chunks removed.

Uses a separate collection prefix (day06_reingest_test) so the benchmark indexes
are untouched. Run from starter/:  python -m scripts.reingest_change_test
"""
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from src.chunking import by_paragraph
from src.embeddings import SentenceTransformerEmbedder
from src.ingestion import load_pdf
from src.run import DEVICE, DOC_ID, MODEL, PAGE_RANGE, PDF, RESULTS, SOURCE
from src.store import ChromaStore

pages = load_pdf(PDF, DOC_ID, SOURCE, PAGE_RANGE)
emb = SentenceTransformerEmbedder(MODEL, device=DEVICE)
tmp = Path(tempfile.mkdtemp(prefix="chroma_reingest_"))
store = ChromaStore(tmp, emb.dimensions, collection_prefix="day06_reingest_test")

v1 = [c for p in pages for c in by_paragraph(p, 800)]
r1 = store.upsert("B", v1, emb.embed_documents([c.text for c in v1]), MODEL)
r2 = store.upsert("B", v1, emb.embed_documents([c.text for c in v1]), MODEL)

# Simulate a new document version: page 170 is shortened to its first paragraph.
changed = [replace(p, text=p.text.split("\n")[0] + "\nRevised text for version 2.") if p.page == 170 else p
           for p in pages]
v2 = [c for p in changed for c in by_paragraph(p, 800)]
r3 = store.upsert("B", v2, emb.embed_documents([c.text for c in v2]), MODEL)

report = {
    "v1_chunks": len(v1), "first_ingest": r1, "same_version_reingest": r2,
    "v2_chunks": len(v2), "changed_version_ingest": r3,
    "ok_no_duplicates": r2["after"] == len(v1) and r2["written"] == 0,
    "ok_stale_removed": r3["after"] == len(v2) and r3["removed_stale"] > 0,
}
print(json.dumps(report, indent=1))
(RESULTS / "reingest_test.json").write_text(json.dumps(report, indent=1))
shutil.rmtree(tmp)
