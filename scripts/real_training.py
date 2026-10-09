"""Experiment 9b: should the starting model also train on real resumes?

Experiment 9 showed that teaching the network 10 corrected real resumes
lifts it from 0.79 to 0.86 of real lines. This trains the network the way
experiment 7 does (classic template, 40 generated and 8 designer formats,
10 of 16 personas, seed 0) with 0, 300 or 1,500 real LiveCareer resumes
added, and tests each on:

  real        500 real resumes none of them trained on (the same 500 as
              experiment 9's teaching test)
  synthetic   experiment 7's four held-out groups (people and formats never
              trained on), so a gain on real resumes cannot hide a loss here
  your resume with --private-labels/--private-file, written under private/ only

    python scripts/real_training.py --private-labels private/x.lines.json --private-file private/x.pdf
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

OUT = ROOT / "results" / "real"


def real_docs(docs: list[dict]) -> list[tuple]:
    out = []
    for d in docs:
        keep = [j for j, g in enumerate(d["gold"]) if g is not None]
        if keep:
            out.append(([d["lines"][j] for j in keep], [d["gold"][j] for j in keep], [d["geo"][j] for j in keep]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mix", default="0,300,1500")
    ap.add_argument("--private-labels", type=Path)
    ap.add_argument("--private-file", type=Path)
    a = ap.parse_args()
    from ats_sim.data import RESUME_DIR, load_personas
    from ats_sim.formats import (HELD_OUT_DESIGNER, HELD_OUT_FORMATS, REFERENCE_FORMATS, TRAIN_DESIGNER,
                                 TRAIN_FORMATS)
    from ats_sim.learn.corpus import documents, format_documents
    from ats_sim.learn.tagger import LineTagger
    from ats_sim.render import HELD_OUT_TEMPLATES

    docs = R.load_docs(4)
    order = np.random.default_rng(0).permutation(len(docs))  # as experiment 9
    test = [docs[i] for i in order[:500]]
    pool = real_docs([docs[i] for i in order[500:]])

    plist = load_personas()
    personas = {p["id"]: p for p in plist}
    templates = documents(templates=("classic", *HELD_OUT_TEMPLATES))
    generated = format_documents(TRAIN_FORMATS + HELD_OUT_FORMATS + TRAIN_DESIGNER + HELD_OUT_DESIGNER
                                 + REFERENCE_FORMATS, per_persona=2, cache=RESUME_DIR)
    ids = [p["id"] for p in plist]
    np.random.default_rng(0).shuffle(ids)  # experiment 7's seed-0 split
    train_ids, test_ids = set(ids[:10]), set(ids[10:])
    tests = {"hand-written": {k: d for k, d in templates.items() if k[1] in HELD_OUT_TEMPLATES and k[0] in test_ids}}
    for g, names in (("generated", HELD_OUT_FORMATS), ("designer", HELD_OUT_DESIGNER), ("reference", REFERENCE_FORMATS)):
        tests[g] = {k: d for k, d in generated.items() if k[1] in set(names) and k[0] in test_ids}
    train = [d for k, d in templates.items() if k[1] == "classic" and k[0] in train_ids]
    train += [d for k, d in generated.items() if k[1] in set(TRAIN_FORMATS) | set(TRAIN_DESIGNER) and k[0] in train_ids]

    rows, private = [], []
    rng = np.random.default_rng(1)
    for n in map(int, a.mix.split(",")):
        extra = [pool[i] for i in rng.choice(len(pool), size=n, replace=False)] if n else []
        tagger = LineTagger(use_geometry=False, seed=0).fit(train + extra)
        row = {"real_resumes_in_training": n,
               "real_line_acc": R.score([tagger.predict(d["lines"], d["geo"]) for d in test], test)["line_acc"]}
        for g, d in tests.items():
            f1, acc = G.scores(tagger, d, personas)
            row[f"{g}_line_acc"], row[f"{g}_f1"] = round(acc, 3), round(f1, 3)
        rows.append(row)
        print(row, flush=True)
        if a.private_labels and a.private_file:
            private.append({"real_resumes_in_training": n, **G.private_score(tagger, a.private_labels, a.private_file)})
            print("  your resume:", private[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mix.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if private:
        (ROOT / "private" / "real_training_private.json").write_text(json.dumps(private, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
