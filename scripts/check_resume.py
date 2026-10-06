"""Run every parser and scorer on one resume and write a report.

    python scripts/check_resume.py my_resume.pdf
    python scripts/check_resume.py my_resume.pdf --gold my_resume.gold.json --authorized yes --public-pool data/kaggle/Resume.csv

The report goes to private/ (gitignored) by default. It shows what each
parser extracted, parsing risks (headings a naive parser does not know,
unmappable glyphs, hidden text, columns), skills found by the curated list
and by SkillNer, knockout results, and the resume's score and rank against
each posting. `--gold` takes a hand-written answer key in the same format as
data/personas.json and adds per-parser accuracy.

This is a simulator modeled on documented ATS behavior; it does not say how
any real vendor's system would treat the resume.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ats_sim.data import load_kaggle_resumes, load_personas, resume_path  # noqa: E402
from ats_sim.engines import (  # noqa: E402
    ATTEMPTED, OpenResumeParser, PyresparserParser, SkillNerScorer, skillner_available, skillner_skills, vote,
)
from ats_sim.evaluate import LENIENT_FIELDS, micro, score_resume_lenient  # noqa: E402
from ats_sim.jd import analyze_job, load_jobs  # noqa: E402
from ats_sim.knockout import apply_knockouts  # noqa: E402
from ats_sim.parser import _HEADING_LOOKUP, extract_text, find_gutter, normalize_heading, parse_resume  # noqa: E402
from ats_sim.scorers import EmbeddingScorer, KeywordScorer, TfidfScorer  # noqa: E402
from ats_sim.skills import default_taxonomy  # noqa: E402

FIELDS = ("name", "email", "phone", "degree_level", "field_of_study", "school", "grad_date", "gpa")


def show(v, width=60) -> str:
    if v is None or v == [] or v == "":
        return "*(none)*"
    s = str(v).replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= width else s[: width - 3] + "..."


def likely_headings(text: str) -> list[str]:
    """Short lines that look like section headings (ALL CAPS, or Title Case
    with no sentence punctuation)."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        words = s.split()
        if not (1 <= len(words) <= 5) or re.search(r"[.,;@|\d]", s) or len(s) < 4:
            continue
        if s.isupper() or all(w[0].isupper() or w.lower() in {"and", "of", "&"} for w in words):
            out.append(s)
    return out


def diagnostics(path: Path, naive_text: str) -> list[str]:
    notes = []
    known = [h for h in likely_headings(naive_text) if normalize_heading(h) in _HEADING_LOOKUP]
    unknown = [h for h in likely_headings(naive_text) if normalize_heading(h) not in _HEADING_LOOKUP
               and (h.isupper())]
    notes.append(f"Headings the naive parser recognizes: {', '.join(known) or 'none'}.")
    if unknown:
        notes.append("ALL-CAPS lines that look like headings but are not in the naive parser's list: "
                     + ", ".join(f'"{h}"' for h in unknown)
                     + ". A heading-list parser files their content under the previous section; "
                       "a parser that detects headings by formatting (like OpenResume) is unaffected.")
    cid = len(re.findall(r"\(cid:\d+\)", naive_text))
    if cid:
        notes.append(f"{cid} glyphs extracted as '(cid:N)' (characters the PDF does not map to Unicode, "
                     "usually bullets or icons). Harmless unless a list depends on them as separators.")
    if path.suffix.lower() == ".pdf":
        import pdfplumber

        visible = extract_text(path, drop_invisible=True)
        hidden = len(re.sub(r"\s", "", naive_text)) - len(re.sub(r"\s", "", visible))
        notes.append("No white or tiny hidden text found." if hidden <= 0 else
                     f"{hidden} characters of white or tiny text found; a human reviewer would not see them.")
        with pdfplumber.open(str(path)) as pdf:
            notes.append(f"{len(pdf.pages)} page(s).")
            cols = [i + 1 for i, pg in enumerate(pdf.pages) if find_gutter(pg.extract_words(), pg.width)]
            tables = [i + 1 for i, pg in enumerate(pdf.pages) if pg.find_tables()]
        if cols:
            notes.append(f"Two-column layout detected on page(s) {cols}: text-order parsers will interleave columns.")
        else:
            notes.append("No column layout detected: reading order is the same for every parser.")
        if tables:
            notes.append(f"Ruled tables detected on page(s) {tables}.")
    return notes


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resume")
    ap.add_argument("--gold", help="hand-written answer key (data/personas.json format) for per-parser accuracy")
    ap.add_argument("--jobs-dir", action="append", help="posting folders (default: data/jobs and data/jobs_extra)")
    ap.add_argument("--authorized", choices=["yes", "no", "unknown"], default="unknown",
                    help="answer to the work-authorization question (not on a resume)")
    ap.add_argument("--needs-sponsorship", choices=["yes", "no", "unknown"], default="unknown")
    ap.add_argument("--public-pool", help="Kaggle-format resume CSV to add to the ranking pool")
    ap.add_argument("--no-skillner-ranking", action="store_true",
                    help="skip the SkillNer scorer when ranking (it annotates every pool resume and is slow)")
    ap.add_argument("--out", default=str(ROOT / "private"))
    args = ap.parse_args()

    path = Path(args.resume).resolve()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"parsing {path.name}")

    parsed = {"naive": parse_resume(path), "layout_aware": parse_resume(path, layout_aware=True)}
    for engine in (OpenResumeParser(), PyresparserParser()):
        if engine.available() and path.suffix.lower().lstrip(".") in engine.formats:
            parsed[engine.name] = engine.parse_many([path]).get(str(path))
    parsed = {k: v for k, v in parsed.items() if v is not None}
    members = [m for m in ("layout_aware", "openresume", "pyresparser") if m in parsed]
    if len(members) >= 2:
        parsed["ensemble"] = vote([parsed[m] for m in members], members)
    names = list(parsed)

    md = [f"# Resume check: {path.name}", "",
          "A simulator modeled on documented ATS behavior, not a prediction of any real vendor's system.", ""]

    md += ["## Parsing risks", ""] + [f"- {n}" for n in diagnostics(path, parsed["naive"].raw_text)] + [""]

    md += ["## What each parser extracted", "", "| field | " + " | ".join(names) + " |",
           "|---|" + "---|" * len(names)]
    for f in FIELDS:
        md.append(f"| {f} | " + " | ".join(show(getattr(parsed[n], f)) for n in names) + " |")
    md.append("| experience | " + " | ".join(
        show("; ".join(f"{e.title} @ {e.company}" for e in parsed[n].experience), 90) for n in names) + " |")
    md.append("| skills (count) | " + " | ".join(str(len(parsed[n].skills)) for n in names) + " |")
    md.append("")

    if args.gold:
        gold = json.loads(Path(args.gold).read_text())
        md += ["## Accuracy against your answer key (lenient matching)", "",
               "| parser | F1 | " + " | ".join(LENIENT_FIELDS) + " |", "|---|---|" + "---|" * len(LENIENT_FIELDS)]
        for n in names:
            counts = score_resume_lenient(gold, parsed[n])
            attempted = ATTEMPTED.get(n) or set(LENIENT_FIELDS)
            cells = []
            for f in LENIENT_FIELDS:
                c = counts[f]
                if f not in attempted:
                    cells.append("n/a")
                elif c.tp + c.fn + c.fp == 0:
                    cells.append("-")
                else:
                    cells.append(f"{c.tp}/{c.tp + c.fn}" + (f" (+{c.fp} wrong)" if c.fp else ""))
            f1 = micro([counts], [f for f in LENIENT_FIELDS if f in attempted]).f1
            md.append(f"| {n} | {f1:.2f} | " + " | ".join(cells) + " |")
        md += ["", "Cells show correct/expected; '+N wrong' counts extra or incorrect values.", ""]

    text = parsed["naive"].raw_text
    tax = default_taxonomy().find_all(text)
    md += ["## Skills found in the text", "",
           f"- Curated list ({len(default_taxonomy().skills)} skills): " + (", ".join(sorted(tax)) or "none")]
    if skillner_available():
        sk = sorted(skillner_skills(text))
        md.append(f"- SkillNer / EMSI-Lightcast taxonomy ({len(sk)} found): " + ", ".join(sk))
    md.append("")

    # ---- scoring against postings
    dirs = args.jobs_dir or [str(ROOT / "data" / "jobs"), str(ROOT / "data" / "jobs_extra")]
    jobs = [j for d in dirs for j in load_jobs(d)]
    pool = {}
    for p in load_personas():
        rp = resume_path(p["id"], "single", "pdf")
        if rp.exists():
            pool[p["id"]] = parse_resume(rp).raw_text
    if args.public_pool:
        pool.update(dict(load_kaggle_resumes(args.public_pool, limit=50,
                                             category=["ENGINEERING", "INFORMATION-TECHNOLOGY", "AVIATION",
                                                       "AUTOMOBILE", "HEALTHCARE"])))
    corpus = list(pool.values()) + [j.text for j in jobs] + [text]
    scorers = [KeywordScorer(), TfidfScorer(), EmbeddingScorer()]
    if skillner_available() and not args.no_skillner_ranking:
        scorers.append(SkillNerScorer())
    scorers = [s.fit(corpus) for s in scorers]
    answer = {"yes": True, "no": False, "unknown": None}
    application = {"work_authorized": answer[args.authorized], "needs_sponsorship": answer[args.needs_sponsorship]}

    md += ["## Against each posting", "",
           f"Ranking pool: your resume plus {len(pool)} others "
           f"({'16 synthetic' if not args.public_pool else '16 synthetic and public'} resumes). "
           "Rank 1 is best. Knockouts use what the parser extracted, as an uncorrected prefilled form would; "
           f"work authorization: {args.authorized}.", ""]
    for job in jobs:
        a = analyze_job(job)
        md += [f"### {job.title}", ""]
        for pname in ("naive", "ensemble") if "ensemble" in parsed else ("naive",):
            ko = apply_knockouts(parsed[pname], job.knockouts, application)
            why = "; ".join(ko.reasons + [f"missing {m}" for m in ko.missing]) or "all rules passed"
            md.append(f"- Knockout ({pname} parse): **{ko.status}** ({why})")
        md += ["", "| scorer | your score | rank | best other score |", "|---|---|---|---|"]
        for s in scorers:
            mine = s.score(text, a)
            others = [s.score(t, a) for t in pool.values()]
            rank = 1 + sum(o > mine + 1e-12 for o in others)
            label = s.name if s.name != "embedding" else f"embedding ({s.backend})"
            md.append(f"| {label} | {mine:.3f} | {rank} of {len(others) + 1} | {max(others):.3f} |")
        kw = scorers[0].explain(text, a)
        md += ["", f"- Posting terms found: {', '.join(kw.matched) or 'none'}",
               f"- Posting terms not found verbatim: {', '.join(kw.missing) or 'none'}", ""]

    out = out_dir / f"{path.stem}.report.md"
    out.write_text("\n".join(md))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
