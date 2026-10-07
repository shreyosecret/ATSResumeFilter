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

from ats_sim.evaluate import LENIENT_FIELDS  # noqa: E402
from ats_sim.jd import load_jobs  # noqa: E402
from ats_sim.report import FIELDS, Analyzer, load_posting_file  # noqa: E402

ICONS = {"ok": "OK", "info": "Note", "warn": "Warning", "bad": "Problem"}


def show(v, width=60) -> str:
    if v is None or v == [] or v == "":
        return "*(none)*"
    s = str(v).replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= width else s[: width - 3] + "..."


def to_markdown(r: dict, authorized: str) -> str:
    names = list(r["parsers"])
    md = [f"# Resume check: {r['file']}", "",
          "A simulator modeled on documented ATS behavior, not a prediction of any real vendor's system.", "",
          "## Parsing risks", ""]
    md += [f"- **{ICONS[x['level']]}: {x['title']}.** {x['detail']}" for x in r["risks"]] + [""]

    md += ["## What each parser extracted", "", "| field | " + " | ".join(names) + " |",
           "|---|" + "---|" * len(names)]
    for f in FIELDS:
        md.append(f"| {f} | " + " | ".join(show(r["parsers"][n][f]) for n in names) + " |")
    md.append("| experience | " + " | ".join(
        show("; ".join(f"{e['title']} @ {e['company']}" for e in r["parsers"][n]["experience"]), 90)
        for n in names) + " |")
    md += ["| skills (count) | " + " | ".join(str(len(r["parsers"][n]["skills"])) for n in names) + " |", ""]

    if "accuracy" in r:
        md += ["## Accuracy against your answer key (lenient matching)", "",
               "| parser | F1 | " + " | ".join(LENIENT_FIELDS) + " |", "|---|---|" + "---|" * len(LENIENT_FIELDS)]
        for n, acc in r["accuracy"].items():
            cells = []
            for f in LENIENT_FIELDS:
                c = acc["fields"][f]
                if c is None:
                    cells.append("n/a")
                elif c["tp"] + c["fn"] + c["fp"] == 0:
                    cells.append("-")
                else:
                    cells.append(f"{c['tp']}/{c['tp'] + c['fn']}" + (f" (+{c['fp']} wrong)" if c["fp"] else ""))
            md.append(f"| {n} | {acc['f1']:.2f} | " + " | ".join(cells) + " |")
        md += ["", "Cells show correct/expected; '+N wrong' counts extra or incorrect values.", ""]

    md += ["## Skills found in the text", "",
           f"- Curated list: " + (", ".join(r["skills"]["curated"]) or "none")]
    if "skillner" in r["skills"]:
        md.append(f"- SkillNer / EMSI-Lightcast taxonomy ({len(r['skills']['skillner'])} found): "
                  + ", ".join(r["skills"]["skillner"]))
    md.append("")

    pool = r["pool"]
    md += ["## Against each posting", "",
           f"Ranking pool: your resume plus {pool['size']} others ({pool['synthetic']} synthetic, "
           f"{pool['public']} public). Rank 1 is best. Knockouts use what the parser extracted, as an uncorrected "
           f"prefilled form would; work authorization: {authorized}.", ""]
    for m in r["matches"]:
        md += [f"### {m['posting']['title']}", ""]
        for pname, ko in m["knockouts"].items():
            why = "; ".join(ko["reasons"] + [f"missing {x}" for x in ko["missing"]]) or "all rules passed"
            md.append(f"- Knockout ({pname} parse): **{ko['status']}** ({why})")
        md += ["", "| scorer | your score | rank | best other score |", "|---|---|---|---|"]
        for s in m["scores"]:
            label = s["name"] if s["name"] != "embedding" else f"embedding ({s['backend']})"
            md.append(f"| {label} | {s['score']:.3f} | {s['rank']} of {s['of']} | {s['best_other']:.3f} |")
        md += ["", f"- Posting terms found: {', '.join(m['matched']) or 'none'}",
               f"- Posting terms not found verbatim: {', '.join(m['missing']) or 'none'}", ""]
    return "\n".join(md)


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
    answer = {"yes": True, "no": False, "unknown": None}
    result = analyzer.analyze(
        path, application={"work_authorized": answer[args.authorized],
                           "needs_sponsorship": answer[args.needs_sponsorship]},
        gold=json.loads(Path(args.gold).read_text()) if args.gold else None)
    out = out_dir / f"{path.stem}.report.md"
    out.write_text(to_markdown(result, args.authorized))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
