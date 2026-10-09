"""Experiment 9c: the app's starting model with and without real resumes.

Experiment 9b found that a few real resumes in training (about 3% of the
documents) help on real resumes without costing anything on synthetic
layouts, while more cost the unusual layouts. This checks the model the app
actually ships, trained on the full synthetic corpus, with 0 or k real
resumes (k drawn from the resumes experiment 9 did not test on), on data
none of them trained on: the 500 test resumes of experiment 9, the 54 JSON
Resume themes (experiment 10) and, with --private-*, a hand-labeled resume
(written under private/ only). --write-ids saves the chosen resumes'
IDs to data/livecareer_train_ids.json for the starting model.

    python scripts/real_shipping_check.py --k 0,30,90 --write-ids 90
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

import geometry_ablation as G  # noqa: E402
import real_resumes as R  # noqa: E402
from real_training import real_docs  # noqa: E402

IDS = ROOT / "data" / "livecareer_train_ids.json"


def themes_score(tagger) -> dict:
    from ats_sim.data import load_personas
    from ats_sim.evaluate import micro, score_resume
    from ats_sim.jsonresume import label_lines, theme_headings
    from ats_sim.learn.geometry import read
    from ats_sim.learn.tagger import parse_with_tagger
    from jsonresume_formats import BUILD, PDF_DIR

    personas = {p["id"]: p for p in load_personas()}
    counts, hits, total = [], 0, 0
    for d in sorted(PDF_DIR.iterdir()):
        pdfs = sorted(d.glob("*.pdf"))
        if len(pdfs) < len(personas):
            continue
        for pdf in pdfs:
            p = personas[pdf.stem]
            rows = read(pdf)
            lines = [r.text for r in rows]
            if sum(len(x) for x in lines) < 200:
                continue
            html = (BUILD / "html" / d.name / f"{pdf.stem}.html").read_text(encoding="utf-8", errors="replace")
            gold = label_lines(lines, p, theme_headings(html, p))
            parsed, _, pred = parse_with_tagger("\n".join(lines), tagger, geo=[r.geo for r in rows])
            counts.append(score_resume(p, parsed))
            hits += sum(a == b for a, b in zip(pred, gold))
            total += len(gold)
    return {"themes_f1": round(micro(counts).f1, 3), "themes_line_acc": round(hits / total, 3)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", default="0,30,90")
    ap.add_argument("--write-ids", type=int)
    ap.add_argument("--private-labels", type=Path)
    ap.add_argument("--private-file", type=Path)
    a = ap.parse_args()
    from ats_sim.learn.tagger import LineTagger

    docs = R.load_docs(4)
    order = np.random.default_rng(0).permutation(len(docs))
    test = [docs[i] for i in order[:500]]
    pool_docs = [docs[i] for i in order[500:]]
    pick = np.random.default_rng(7).permutation(len(pool_docs))  # the first k of one fixed order
    if a.write_ids:
        chosen = [pool_docs[i] for i in pick[:a.write_ids]]
        IDS.write_text(json.dumps({
            "source": "Kaggle snehaanbhawal/resume-dataset (CC0 1.0) via huggingface.co/datasets/opensporks/resumes",
            "why": "real resumes the starting model learns from (experiment 9c); none is in experiment 9's 500 test resumes",
            "resumes": [{"id": d["id"], "category": d["category"]} for d in chosen]}, indent=1), encoding="utf-8")
        print("wrote", IDS)
    corpus = R.base_corpus()
    rows, private = [], []
    for k in map(int, a.k.split(",")):
        extra = real_docs([pool_docs[i] for i in pick[:k]])
        tagger = LineTagger(use_geometry=False).fit(corpus + extra)
        row = {"real_resumes_in_training": k,
               "real_line_acc": R.score([tagger.predict(d["lines"], d["geo"]) for d in test], test)["line_acc"],
               **themes_score(tagger)}
        rows.append(row)
        print(row, flush=True)
        if a.private_labels and a.private_file:
            private.append({"k": k, **G.private_score(tagger, a.private_labels, a.private_file)})
            print("  your resume:", private[-1], flush=True)
    (ROOT / "results" / "real" / "shipping.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if private:
        (ROOT / "private" / "real_shipping_private.json").write_text(json.dumps(private, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
