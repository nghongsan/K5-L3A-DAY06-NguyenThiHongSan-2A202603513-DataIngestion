"""Day 06 pipeline entry point.

Usage (from starter/):
    python -m src.run ingest            # read PDF, verify benchmark evidence, chunk, embed, store (A/B/C)
    python -m src.run retrieve --split dev    # run dev questions only (choose strategy here)
    python -m src.run retrieve --split test   # run test questions after the choice is frozen
    python -m src.run audit             # export samples for manual coherence/metadata/grounding labels
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .chunking import by_paragraph, fixed_size
from .evaluation import evaluate_query, norm, summarize
from .ingestion import load_pdf, save_pages
from .models import Chunk, DocumentPage

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "data/raw/Introduction_to_Python_Programming-WEB.pdf"
SOURCE = "data/raw/Introduction_to_Python_Programming-WEB.pdf"
DOC_ID = "openstax-intro-python"
PAGE_RANGE = (95, 174)  # chapters 4 (Decisions), 5 (Loops), 6 (Functions)
BENCHMARK = ROOT / "benchmark/questions.json"
RESULTS = ROOT / "results"
CHROMA_PATH = ROOT / "chroma_db"
MODEL = "intfloat/multilingual-e5-small"
DEVICE = "cpu"  # MPS crashes on macOS 14.4 with torch 2.15 (NSInvalidArgumentException), logged in report

STRATEGIES = {
    "A": {"chunking": "fixed_size", "chunk_size": 500, "overlap": 50, "filter": False, "index": "A"},
    "B": {"chunking": "by_paragraph", "chunk_size": 800, "overlap": 0, "filter": False, "index": "B"},
    # C = identical chunks/vectors to B; only difference: metadata filter when the question has one
    "C": {"chunking": "by_paragraph", "chunk_size": 800, "overlap": 0, "filter": True, "index": "C"},
}


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _load_pages() -> tuple[list[DocumentPage], list[dict]]:
    if not PDF.exists():
        sys.exit(f"Corpus missing: {PDF}. Run scripts/download_corpus.sh first.")
    log: list[dict] = []
    pages = load_pdf(PDF, DOC_ID, SOURCE, PAGE_RANGE, log=log)
    return pages, log


def _chunk(pages: list[DocumentPage], name: str) -> list[Chunk]:
    cfg = STRATEGIES[name]
    if cfg["chunking"] == "fixed_size":
        return [c for p in pages for c in fixed_size(p, cfg["chunk_size"], cfg["overlap"], strategy=name)]
    return [c for p in pages for c in by_paragraph(p, cfg["chunk_size"], strategy="B")]


def _stats(chunks: list[Chunk], tokenizer=None) -> dict:
    lengths = [len(c.text) for c in chunks]
    tokens = ([len(tokenizer.encode("passage: " + c.text)) for c in chunks] if tokenizer else [])
    return {"chunks": len(chunks), "chars_total": sum(lengths),
            "tokens_total": sum(tokens), "tokens_max": max(tokens) if tokens else None,
            "chunks_over_512_tokens": sum(t > 512 for t in tokens), "len_min": min(lengths),
            "len_median": statistics.median(lengths), "len_mean": round(statistics.mean(lengths), 1),
            "len_max": max(lengths),
            "len_p10": sorted(lengths)[len(lengths) // 10], "len_p90": sorted(lengths)[len(lengths) * 9 // 10]}


def verify_benchmark(pages: list[DocumentPage]) -> list[dict]:
    """Every evidence quote must exist on its gold page after normalization."""
    by_page = {p.page: norm(p.text) for p in pages}
    bench = json.loads(BENCHMARK.read_text())
    report = []
    for q in bench["questions"]:
        for g in q["gold"]:
            ok = norm(g["evidence_quote"]) in by_page.get(g["page"], "")
            report.append({"id": q["id"], "page": g["page"], "evidence_found_on_page": ok})
    bad = [r for r in report if not r["evidence_found_on_page"]]
    if bad:
        raise SystemExit(f"Benchmark evidence not found on gold page: {bad}")
    splits = [q["split"] for q in bench["questions"]]
    filt = [q for q in bench["questions"] if q.get("filter")]
    assert splits.count("dev") >= 15 and splits.count("test") >= 5, "need >=15 dev / >=5 test"
    assert len(filt) >= 3 and any(q["split"] == "test" for q in filt), "need >=3 filter questions, >=1 test"
    return report


def cmd_ingest(_args) -> None:
    from .embeddings import SentenceTransformerEmbedder
    from .store import ChromaStore

    t0 = time.perf_counter()
    pages, log = _load_pages()
    t_read = time.perf_counter() - t0
    if len(pages) < 30:
        raise SystemExit(f"Only {len(pages)} content pages; need >= 30")
    save_pages(pages, RESULTS / "pages.jsonl")
    (RESULTS / "ingest_log.json").write_text(json.dumps(log, indent=1))
    evidence_report = verify_benchmark(pages)
    (RESULTS / "benchmark_evidence_check.json").write_text(json.dumps(evidence_report, indent=1))
    print(f"pages: {len(pages)} content pages, {sum(len(p.text) for p in pages)} chars; "
          f"evidence verified for {len(evidence_report)} gold entries")

    t0 = time.perf_counter()
    embedder = SentenceTransformerEmbedder(MODEL, device=DEVICE)
    t_model = time.perf_counter() - t0
    store = ChromaStore(CHROMA_PATH, embedder.dimensions)
    run_info = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(), "platform": platform.platform(),
        "embedding_model": MODEL, "dimensions": embedder.dimensions,
        "embedding_provider": f"local sentence-transformers on {DEVICE}, cost $0",
        "vector_store": f"chromadb {store.chroma_version} PersistentClient, HNSW, cosine",
        "page_range": PAGE_RANGE, "content_pages": len(pages), "read_seconds": round(t_read, 2),
        "model_load_seconds": round(t_model, 2), "strategies": {},
    }
    vectors_cache: dict[str, list[list[float]]] = {}
    chunks_cache: dict[str, list[Chunk]] = {}
    for name, cfg in STRATEGIES.items():
        t0 = time.perf_counter()
        base = "A" if cfg["chunking"] == "fixed_size" else "B"
        if base not in chunks_cache:
            chunks_cache[base] = _chunk(pages, base)
            t_chunk = time.perf_counter() - t0
            t1 = time.perf_counter()
            vectors_cache[base] = embedder.embed_documents([c.text for c in chunks_cache[base]])
            t_embed = time.perf_counter() - t1
        else:
            t_chunk = t_embed = 0.0  # C reuses B's chunks and vectors (identical by design)
        chunks, vectors = chunks_cache[base], vectors_cache[base]
        t1 = time.perf_counter()
        first = store.upsert(name, chunks, vectors, MODEL)
        t_store = time.perf_counter() - t1
        # Idempotency check: re-ingesting the same version must not grow the collection.
        second = store.upsert(name, chunks, vectors, MODEL)
        if second["after"] != len(chunks) or first["after"] != len(chunks) or second["written"] != 0:
            raise SystemExit(f"Re-ingest check failed for {name}: {first} / {second}")
        _write_jsonl(RESULTS / f"chunks_{name}.jsonl",
                     [{"chunk_id": c.chunk_id, "page": c.page, **c.metadata, "text": c.text} for c in chunks])
        run_info["strategies"][name] = {
            **cfg, **_stats(chunks, embedder.model.tokenizer), "chunk_seconds": round(t_chunk, 3), "embed_seconds": round(t_embed, 2),
            "store_seconds": round(t_store, 2), "upsert_first": first, "upsert_reingest": second,
            "cost_usd": 0.0,
        }
        print(f"{name}: {len(chunks)} chunks, embed {t_embed:.1f}s, store {t_store:.1f}s, "
              f"re-ingest {second['before']}->{second['after']}, rewritten {second['written']} (no duplicates)")
    (RESULTS / "run_info.json").write_text(json.dumps(run_info, indent=1))


def cmd_retrieve(args) -> None:
    from .embeddings import SentenceTransformerEmbedder
    from .store import ChromaStore

    bench = json.loads(BENCHMARK.read_text())
    questions = [q for q in bench["questions"] if args.split == "all" or q["split"] == args.split]
    embedder = SentenceTransformerEmbedder(MODEL, device=DEVICE)
    store = ChromaStore(CHROMA_PATH, embedder.dimensions)
    page_texts = {json.loads(l)["page"]: json.loads(l)["text"] for l in (RESULTS / "pages.jsonl").open()}
    embedder.embed_query("warm-up query")  # exclude one-off model warm-up from per-query timing
    traces = []
    timing = {}
    for name, cfg in STRATEGIES.items():
        t0 = time.perf_counter()
        for q in questions:
            qv = embedder.embed_query(q["question"])  # question text only: no gold, no answer
            filters = q.get("filter") if cfg["filter"] else None
            hits = store.search(cfg["index"], qv, top_k=3, filters=filters)
            t = evaluate_query(q, hits, page_texts)
            exact = store.exact_top_k(cfg["index"], qv, top_k=3, filters=filters)
            t["ann_equals_exact_top3"] = [h["chunk_id"] for h in hits] == exact
            t["strategy"] = name
            t["filter_applied"] = filters
            traces.append(t)
        timing[name] = round((time.perf_counter() - t0) / len(questions) * 1000, 1)
    _write_jsonl(RESULTS / f"traces_{args.split}.jsonl", traces)
    summary = summarize(traces)
    for name in summary:
        for split in summary[name]:
            summary[name][split]["ms_per_query"] = timing[name]
    (RESULTS / f"metrics_{args.split}.json").write_text(json.dumps(summary, indent=1))
    mism = [(t["strategy"], t["id"]) for t in traces if not t["ann_equals_exact_top3"]]
    print(f"ANN top-3 == exact brute-force top-3: {len(traces) - len(mism)}/{len(traces)} {mism or ''}")
    print(f"{'strategy':8} {'split':5} {'Hit@1':>8} {'EvHit@3':>8} {'PageHit@3':>9} {'split-ev':>8} {'filter ok':>9}")
    for name, splits in summary.items():
        for split, m in splits.items():
            fo = f"{m['filter_compliant']}/{m['filter_questions']}" if m["filter_questions"] else "N/A"
            print(f"{name:8} {split:5} {m['hit@1']:>3}/{m['N']:<4} {m['evidence_hit@3']:>3}/{m['N']:<4} "
                  f"{m['page_hit@3']:>4}/{m['N']:<4} {m['split_evidence_failures']:>8} {fo:>9}")


def _offset_of_sample(page: DocumentPage) -> int:
    """Pre-registered coherence position: first prose line starting after mid-page."""
    mid = len(page.text) // 2
    pos = 0
    for line in page.text.split("\n"):
        if pos >= mid and len(line) > 60 and not line.startswith(("•", "#", "a.", "b.", "c.")):
            return pos
        pos += len(line) + 1
    return mid


def cmd_audit(_args) -> None:
    """Export sheets for manual labels (coherence, metadata, grounding)."""
    pages = {json.loads(l)["page"]: json.loads(l) for l in (RESULTS / "pages.jsonl").open()}
    audit = RESULTS / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    # Coherence: 10 pages chosen by rule BEFORE looking at scores: every 8th content page.
    sample_pages = sorted(pages)[::8][:10]
    rows = []
    for name in ("A", "B"):
        chunks = [json.loads(l) for l in (RESULTS / f"chunks_{name}.jsonl").open()]
        for pno in sample_pages:
            p = pages[pno]
            off = _offset_of_sample(DocumentPage(DOC_ID, SOURCE, pno, p["text"], p["metadata"]))
            covering = [c for c in chunks if c["page"] == pno and c["char_start"] <= off < c["char_end"]]
            c = covering[0]
            rows.append({"strategy": name, "page": pno, "char_offset": off,
                         "position_text": p["text"][off:off + 80].replace("\n", " "),
                         "chunk_id": c["chunk_id"], "chunk_text": c["text"], "score_0_2": "", "reason": ""})
    with (audit / "coherence_to_label.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"coherence sample pages: {sample_pages}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest").set_defaults(func=cmd_ingest)
    r = sub.add_parser("retrieve")
    r.add_argument("--split", choices=["dev", "test", "all"], required=True)
    r.set_defaults(func=cmd_retrieve)
    sub.add_parser("audit").set_defaults(func=cmd_audit)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
