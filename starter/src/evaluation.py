"""Evaluate retrieved evidence (Hit@1, Evidence Hit@3) and keep per-query traces.

A retrieved chunk is a hit for a question when, for at least one gold alternative,
document_id == gold source, page == gold page and the chunk contains the FULL
evidence quote after whitespace/case normalization. Coherence and grounding are
NOT inferred here: they are labelled manually (see results/audit/).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def chunk_matches(gold: dict[str, Any], hit: dict[str, Any]) -> dict[str, bool]:
    md = hit["metadata"]
    page_ok = md.get("document_id") == gold["source_id"] and int(md.get("page")) == int(gold["page"])
    ev_ok = norm(gold["evidence_quote"]) in norm(hit["text"])
    return {"page_match": page_ok, "evidence_full": ev_ok, "hit": page_ok and ev_ok}


def evidence_span(page_text: str, quote: str) -> tuple[int, int] | None:
    """Locate the quote in the raw page text, tolerant to whitespace/line breaks."""
    pattern = r"\s+".join(re.escape(w) for w in quote.split())
    m = re.search(pattern, page_text, flags=re.I)
    return (m.start(), m.end()) if m else None


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]],
                   page_texts: dict[int, str] | None = None) -> dict[str, Any]:
    per_hit = []
    for h in hits:
        best = {"page_match": False, "evidence_full": False, "hit": False, "gold_page": None}
        for g in question["gold"]:
            m = chunk_matches(g, h)
            if m["hit"] or (m["page_match"] and not best["page_match"]):
                best = {**m, "gold_page": g["page"]}
            if m["hit"]:
                break
        per_hit.append(best)
    hit1 = bool(per_hit) and per_hit[0]["hit"]
    hit3 = any(p["hit"] for p in per_hit[:3])
    # Diagnose evidence split across chunks: no single top-3 chunk holds the full
    # quote, but the union of the character ranges of top-3 chunks from the gold
    # page covers the quote's location in the page (diagnostic only, not a hit).
    split = False
    if not hit3 and page_texts:
        for g in question["gold"]:
            span = evidence_span(page_texts.get(int(g["page"]), ""), g["evidence_quote"])
            if not span:
                continue
            ranges = sorted((h["metadata"]["char_start"], h["metadata"]["char_end"])
                            for h in hits[:3] if int(h["metadata"]["page"]) == int(g["page"]))
            if not ranges:
                continue
            covered, reach = False, None
            for s, e in ranges:
                if reach is None:
                    if s <= span[0]:
                        reach = e
                elif s <= reach:
                    reach = max(reach, e)
                if reach is not None and reach >= span[1]:
                    covered = True
            split = split or covered
    filt = question.get("filter")
    filter_ok = None
    if filt:
        filter_ok = all(all(h["metadata"].get(k) == v for k, v in filt.items()) for h in hits[:3])
    return {
        "id": question["id"], "split": question["split"], "type": question.get("type"),
        "question": question["question"], "filter_requested": filt,
        "gold": question["gold"], "expected_answer": question["expected_answer"],
        "hit@1": hit1, "evidence_hit@3": hit3, "page_hit@3": any(p["page_match"] for p in per_hit),
        "evidence_split_across_chunks": split, "filter_compliant": filter_ok,
        "top_k": [{**h, **{"match": p}} for h, p in zip(hits, per_hit)],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and split, with n/N."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out: dict[str, Any] = {}
    for (strategy, split), items in sorted(groups.items()):
        n = len(items)
        h1 = sum(t["hit@1"] for t in items)
        h3 = sum(t["evidence_hit@3"] for t in items)
        p3 = sum(t["page_hit@3"] for t in items)
        filt = [t for t in items if t["filter_requested"]]
        out.setdefault(strategy, {})[split] = {
            "N": n, "hit@1": h1, "evidence_hit@3": h3, "page_hit@3": p3,
            "hit@1_rate": round(h1 / n, 3), "evidence_hit@3_rate": round(h3 / n, 3),
            "split_evidence_failures": sum(t["evidence_split_across_chunks"] for t in items),
            "filter_questions": len(filt),
            "filter_compliant": sum(1 for t in filt if t["filter_compliant"]),
            "ann_equals_exact_top3": sum(1 for t in items if t.get("ann_equals_exact_top3")),
        }
    return out
