"""Build a self-contained HTML results explorer from results/ (run from starter/).

    python -m scripts.build_explorer            # writes report/results_explorer.html
    python -m scripts.build_explorer --body X   # also writes a body-only copy (for hosting wrappers)

The page only displays numbers already stored in results/; it computes nothing new.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from src.run import RESULTS, ROOT

STRATS = ("A", "B", "C")


def load_jsonl(p: Path):
    return [json.loads(l) for l in p.open(encoding="utf-8")]


def collect() -> dict:
    info = json.loads((RESULTS / "run_info.json").read_text())
    metrics = {"dev": json.loads((RESULTS / "metrics_dev.json").read_text()),
               "test": json.loads((RESULTS / "metrics_test.json").read_text())}
    coh = list(csv.DictReader((RESULTS / "audit/coherence_labels.csv").open(encoding="utf-8")))
    grd = list(csv.DictReader((RESULTS / "audit/grounding_labels.csv").open(encoding="utf-8")))
    md = list(csv.DictReader((RESULTS / "audit/metadata_labels.csv").open(encoding="utf-8")))
    reingest = json.loads((RESULTS / "reingest_test.json").read_text())

    rows = []
    for name in STRATS:
        s = info["strategies"][name]
        for split in ("dev", "test"):
            m = metrics[split][name][split]
            rows.append({"strategy": name, "split": split, "N": m["N"], "hit1": m["hit@1"],
                         "hit3": m["evidence_hit@3"], "page3": m["page_hit@3"],
                         "fq": m["filter_questions"], "fok": m["filter_compliant"],
                         "ann": m["ann_equals_exact_top3"], "ms": m["ms_per_query"],
                         "chunks": s["chunks"], "embed_s": s["embed_seconds"]})
    quality = []
    for name in STRATS:
        c = [int(r["score_0_2"]) for r in coh if r["strategy"] == name]
        g = [int(r["grounding_0_2"]) for r in grd if r["strategy"] == name]
        m = [r for r in md if r["strategy"] == name]
        cnt = Counter(g)
        s = info["strategies"][name]
        quality.append({"strategy": name, "coh": round(sum(c) / len(c), 2), "coh_n": len(c),
                        "md_ok": sum(r["complete_and_correct"] == "True" for r in m), "md_n": len(m),
                        "g": [cnt[0], cnt[1], cnt[2]], "g_mean": round(sum(g) / len(g), 2),
                        "tokens": s["tokens_total"], "len_median": s["len_median"]})

    grd_by = {(r["strategy"], r["id"]): r for r in grd}
    questions: dict[str, dict] = {}
    for split in ("dev", "test"):
        for t in load_jsonl(RESULTS / f"traces_{split}.jsonl"):
            q = questions.setdefault(t["id"], {
                "id": t["id"], "split": t["split"], "type": t.get("type"), "question": t["question"],
                "filter": t["filter_requested"], "gold": [{"page": g["page"], "quote": g["evidence_quote"]}
                                                         for g in t["gold"]],
                "answer": t["expected_answer"], "runs": {}})
            g = grd_by.get((t["strategy"], t["id"]))
            q["runs"][t["strategy"]] = {
                "hit1": t["hit@1"], "hit3": t["evidence_hit@3"], "split_ev": t["evidence_split_across_chunks"],
                "filter_ok": t["filter_compliant"], "filter_applied": t.get("filter_applied"),
                "grounding": int(g["grounding_0_2"]) if g else None, "grounding_reason": g["reason"] if g else None,
                "hits": [{"rank": h["rank"], "id": h["chunk_id"].split(":", 2)[-1], "score": h["score"],
                          "page": h["metadata"]["page"], "printed": h["metadata"].get("printed_page"),
                          "chapter": h["metadata"]["chapter"], "section": h["metadata"].get("section"),
                          "section_title": h["metadata"].get("section_title"),
                          "hit": h["match"]["hit"], "page_match": h["match"]["page_match"],
                          "text": h["text"]} for h in t["top_k"]]}
    qs = sorted(questions.values(), key=lambda q: (q["split"] != "dev", q["id"]))
    return {"model": info["embedding_model"], "dims": info["dimensions"], "store": info["vector_store"],
            "run_at": info["run_at"], "rows": rows, "quality": quality, "questions": qs,
            "reingest": {"written": reingest["same_version_reingest"]["written"],
                         "removed": reingest["changed_version_ingest"]["removed_stale"]}}


TEMPLATE = (Path(__file__).with_name("explorer_template.html")).read_text(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", type=Path, help="also write a body-only copy here")
    args = ap.parse_args()
    data = json.dumps(collect(), ensure_ascii=False).replace("</", "<\\/")
    body = TEMPLATE.replace("/*__DATA__*/null", data)
    out = ROOT / "report" / "results_explorer.html"
    out.write_text("<!doctype html>\n<html lang=\"vi\">\n<head>\n<meta charset=\"utf-8\">\n"
                   "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
                   "</head>\n<body>\n" + body + "\n</body>\n</html>\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    if args.body:
        args.body.write_text(body, encoding="utf-8")
        print(f"wrote {args.body}")


if __name__ == "__main__":
    main()
