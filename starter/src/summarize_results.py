"""Aggregate metrics + manual labels into results/summary.md (run from starter/)."""
import csv
import json
from collections import Counter

from .run import RESULTS


def main() -> None:
    info = json.loads((RESULTS / "run_info.json").read_text())
    dev = json.loads((RESULTS / "metrics_dev.json").read_text())
    test = json.loads((RESULTS / "metrics_test.json").read_text())
    coh = list(csv.DictReader((RESULTS / "audit/coherence_labels.csv").open()))
    grd = list(csv.DictReader((RESULTS / "audit/grounding_labels.csv").open()))
    md = list(csv.DictReader((RESULTS / "audit/metadata_labels.csv").open()))
    lines = ["# Results summary", "",
             f"Model `{info['embedding_model']}` ({info['dimensions']}d, {info['embedding_provider']}); "
             f"store {info['vector_store']}; run at {info['run_at']}.", "",
             "| Strategy | Split | Hit@1 | Evidence Hit@3 | Page Hit@3 | Evidence split | Filter compliant | ANN = exact top-3 | Chunks | Embed s | ms/query | Cost |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in ("A", "B", "C"):
        s = info["strategies"][name]
        for split, m in (("dev", dev[name]["dev"]), ("test", test[name]["test"])):
            fc = f"{m['filter_compliant']}/{m['filter_questions']}" if m["filter_questions"] else "N/A"
            lines.append(f"| {name} | {split} | {m['hit@1']}/{m['N']} | {m['evidence_hit@3']}/{m['N']} | "
                         f"{m['page_hit@3']}/{m['N']} | {m['split_evidence_failures']} | {fc} | {m['ann_equals_exact_top3']}/{m['N']} | {s['chunks']} | "
                         f"{s['embed_seconds']} | {m['ms_per_query']} | $0 |")
    lines += ["", "| Strategy | Coherence mean /2 (n) | Metadata complete & correct (test top-3) | Filter compliant (test) | Grounding 0/1/2 | Grounding mean /2 |",
              "|---|---|---|---|---|---|"]
    for name in ("A", "B", "C"):
        c = [int(r["score_0_2"]) for r in coh if r["strategy"] == name]
        g = [int(r["grounding_0_2"]) for r in grd if r["strategy"] == name]
        m = [r for r in md if r["strategy"] == name]
        ok = sum(r["complete_and_correct"] == "True" for r in m)
        f = [r for r in m if r["filter_ok"] != ""]
        fq = {r["id"] for r in f}
        fq_ok = {q for q in fq if all(r["filter_ok"] == "True" for r in f if r["id"] == q)}
        cnt = Counter(g)
        lines.append(f"| {name} | {sum(c)/len(c):.2f} ({len(c)}) | {ok}/{len(m)} | {len(fq_ok)}/{len(fq)} questions | "
                     f"{cnt[0]}/{cnt[1]}/{cnt[2]} | {sum(g)/len(g):.2f} |")
    lines += ["", "Chunk length statistics (characters):", "",
              "| Strategy | chunks | total chars | total tokens (e5 tokenizer) | max tokens | >512 tokens | min | p10 | median | mean | p90 | max |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in ("A", "B", "C"):
        s = info["strategies"][name]
        lines.append(f"| {name} | {s['chunks']} | {s['chars_total']} | {s['tokens_total']} | {s['tokens_max']} | {s['chunks_over_512_tokens']} | {s['len_min']} | {s['len_p10']} | {s['len_median']} | "
                     f"{s['len_mean']} | {s['len_p90']} | {s['len_max']} |")
    re = json.loads((RESULTS / "reingest_test.json").read_text())
    lines += ["", f"Re-ingest: same version rewrote {re['same_version_reingest']['written']} chunks "
              f"(no duplicates: {re['ok_no_duplicates']}); changed page 170 removed {re['changed_version_ingest']['removed_stale']} "
              f"stale chunks (ok: {re['ok_stale_removed']}). Model load {info['model_load_seconds']} s, PDF read {info['read_seconds']} s."]
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
