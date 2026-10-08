"""Run every parser and scorer on one resume and write a Markdown report.

    python scripts/check_resume.py my_resume.pdf
    python scripts/check_resume.py my_resume.pdf --gold my_resume.gold.json --authorized yes --public-pool data/kaggle/Resume.csv
    python scripts/check_resume.py my_resume.pdf --posting real_posting.txt --posting another.txt

The report goes to private/ (gitignored) by default. It shows what each
parser extracted, parsing risks (headings a naive parser does not know,
unmappable glyphs, hidden text, columns), skills found by the curated list
and by SkillNer, knockout results, and the resume's score and rank against
each posting. `--gold` takes a hand-written answer key in the same format as
data/personas.json and adds per-parser accuracy. The desktop app (`ats-sim`)
shows the same analysis interactively.

This is a simulator modeled on documented ATS behavior; it does not say how
any real vendor's system would treat the resume.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ats_sim.jd import load_jobs  # noqa: E402
from ats_sim.report import Analyzer, load_posting_file, to_markdown  # noqa: E402

def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resume")
    ap.add_argument("--gold", help="hand-written answer key (data/personas.json format) for per-parser accuracy")
    ap.add_argument("--jobs-dir", action="append", help="posting folders (default: data/jobs and data/jobs_extra)")
    ap.add_argument("--posting", action="append",
                    help="a real posting saved as .txt (no knockout rules) or .json (data/jobs format); "
                         "replaces the default postings, can repeat")
    ap.add_argument("--authorized", choices=["yes", "no", "unknown"], default="unknown",
                    help="answer to the work-authorization question (not on a resume)")
    ap.add_argument("--needs-sponsorship", choices=["yes", "no", "unknown"], default="unknown")
    ap.add_argument("--public-pool", help="Kaggle-format resume CSV to add to the ranking pool")
    ap.add_argument("--with-skillner-ranking", action="store_true",
                    help="also rank with the SkillNer scorer (it annotates every pool resume and is slow)")
    ap.add_argument("--no-skillner-ranking", action="store_true", help=argparse.SUPPRESS)  # old flag, now default
    ap.add_argument("--learned", action="store_true",
                    help="add the learned (neural) parser from the app's local model folder")
    ap.add_argument("--out", default=str(ROOT / "private"))
    args = ap.parse_args()

    path = Path(args.resume).resolve()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.posting:
        postings = [load_posting_file(p) for p in args.posting]
    elif args.jobs_dir:
        postings = [j for d in args.jobs_dir for j in load_jobs(d)]
    else:
        postings = None
    extra = []
    if args.with_skillner_ranking:
        from ats_sim.engines import SkillNerScorer, skillner_available

        if skillner_available():
            extra.append(SkillNerScorer())
    print(f"analyzing {path.name}")
    analyzer = Analyzer(postings=postings, public_pool=args.public_pool or False, extra_scorers=extra)
    analyzer.warm()
    store = None
    if args.learned:
        from ats_sim.learn.store import ModelStore

        store = ModelStore().load()  # trains the starting model on first use
    answer = {"yes": True, "no": False, "unknown": None}
    result = analyzer.analyze(
        path, application={"work_authorized": answer[args.authorized],
                           "needs_sponsorship": answer[args.needs_sponsorship]},
        gold=json.loads(Path(args.gold).read_text(encoding="utf-8")) if args.gold else None, store=store)
    out = out_dir / f"{path.stem}.report.md"
    out.write_text(to_markdown(result, args.authorized), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
