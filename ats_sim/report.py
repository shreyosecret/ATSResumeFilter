"""Analyze one resume: every parser, parsing risks, skills, knockouts, scores and rank.

Shared by scripts/check_resume.py (Markdown report) and the desktop app
(ats_sim/webapp). Everything returned is plain JSON-ready data.

This is a simulator modeled on documented ATS behavior; it does not say how
any real vendor's system would treat a resume.
"""
from __future__ import annotations

import re
import threading
from dataclasses import asdict
from pathlib import Path

from .data import DATA_DIR, RESUME_DIR, load_kaggle_resumes, load_personas, resume_path
from .engines import (
    ATTEMPTED, OpenResumeParser, PyresparserParser, skillner_available, skillner_skills, vote,
)
from .evaluate import LENIENT_FIELDS, micro, score_resume_lenient
from .jd import analyze_job, load_job, load_jobs
from .knockout import apply_knockouts
from .models import JobPosting, Knockouts, ParsedResume
from .parser import _HEADING_LOOKUP, extract_text, find_gutter, normalize_heading, parse_resume
from .render import RenderOptions, render
from .scorers import EmbeddingScorer, KeywordScorer, TfidfScorer
from .skills import default_taxonomy

FIELDS = ("name", "email", "phone", "degree_level", "field_of_study", "school", "grad_date", "gpa")
FIELD_LABELS = {"name": "Name", "email": "Email", "phone": "Phone", "degree_level": "Degree",
                "field_of_study": "Field of study", "school": "School", "grad_date": "Graduation",
                "gpa": "GPA"}
PARSER_LABELS = {"naive": "Simple parser", "layout_aware": "Layout-aware parser", "openresume": "OpenResume",
                 "pyresparser": "pyresparser", "ensemble": "Combined (vote)"}
PUBLIC_CATEGORIES = ["ENGINEERING", "INFORMATION-TECHNOLOGY", "AVIATION", "AUTOMOBILE", "HEALTHCARE"]


# ------------------------------------------------------------------ parsing

def parse_all(path: str | Path, use_engines: bool = True) -> dict[str, ParsedResume]:
    """Every available parser on one file, plus the field-by-field vote."""
    path = Path(path)
    parsed = {"naive": parse_resume(path), "layout_aware": parse_resume(path, layout_aware=True)}
    if use_engines:
        for engine in (OpenResumeParser(), PyresparserParser()):
            if engine.available() and path.suffix.lower().lstrip(".") in engine.formats:
                try:
                    r = engine.parse_many([path]).get(str(path))
                except Exception:  # an engine failing must not break the report
                    r = None
                if r is not None:
                    parsed[engine.name] = r
    members = [m for m in ("layout_aware", "openresume", "pyresparser") if m in parsed]
    if len(members) >= 2:
        parsed["ensemble"] = vote([parsed[m] for m in members], members)
    return parsed


def fields_of(r: ParsedResume) -> dict:
    d = {f: getattr(r, f) for f in FIELDS}
    d["skills"] = list(r.skills)
    d["experience"] = [asdict(e) for e in r.experience]
    return d


def best_parse(parsed: dict[str, ParsedResume]) -> str:
    return "ensemble" if "ensemble" in parsed else "layout_aware"


def agreement(parsed: dict[str, ParsedResume]) -> dict:
    """Per field: do the parsers that filled it agree (after normalization)?"""
    from .engines import _norm_key

    out = {}
    for f in FIELDS:
        vals = {n: _norm_key(f, getattr(r, f)) for n, r in parsed.items() if n != "ensemble"}
        filled = {n: v for n, v in vals.items() if v is not None}
        distinct = set(filled.values())
        out[f] = {"filled": len(filled), "of": len(vals), "agree": len(distinct) <= 1 and len(filled) > 0}
    return out


# ------------------------------------------------------------------ risks

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


def _risk(level: str, title: str, detail: str) -> dict:
    return {"level": level, "title": title, "detail": detail}


def diagnose(path: str | Path, parsed: dict[str, ParsedResume]) -> list[dict]:
    """Parsing risks, each {level: ok|info|warn|bad, title, detail}."""
    path = Path(path)
    text = parsed["naive"].raw_text
    risks = []
    heads = likely_headings(text)
    known = [h for h in heads if normalize_heading(h) in _HEADING_LOOKUP]
    unknown = [h for h in heads if normalize_heading(h) not in _HEADING_LOOKUP and h.isupper()]
    if unknown:
        risks.append(_risk("warn", "Headings a simple parser will not recognize",
                           ", ".join(f'"{h}"' for h in unknown) + ". A heading-list parser files their content "
                           "under the previous section; parsers that detect headings by formatting are unaffected. "
                           "Recognized: " + (", ".join(known) or "none") + "."))
    elif known:
        risks.append(_risk("ok", "Section headings recognized", ", ".join(known) + "."))

    if any(r.degree_level for r in parsed.values()) and not any(r.field_of_study for r in parsed.values()):
        risks.append(_risk("bad", "Field of study not found",
                           "A degree was found but no parser extracted the major. Parsers commonly look for "
                           "'<degree> in <Field>' (for example 'B.S. in Biomedical Engineering'); without 'in', "
                           "degree-field knockout rules see a missing field."))
    if not any(r.grad_date for r in parsed.values()):
        risks.append(_risk("bad", "Graduation date not found",
                           "No parser found a month and year in the education section. Graduation-window "
                           "knockouts will treat it as missing. Write it like 'May 2027'."))
    schools = {n: r.school for n, r in parsed.items() if r.school and n != "ensemble"}
    if len({str(v).lower() for v in schools.values()}) > 1:
        risks.append(_risk("warn", "Parsers disagree on the school",
                           "; ".join(f"{PARSER_LABELS.get(n, n)}: {v}" for n, v in schools.items())
                           + ". Check the education lines, especially a second school or a date on the same line."))
    names = {n: r.name for n, r in parsed.items() if n != "ensemble"}
    if any(v is None for v in names.values()):
        missing = [PARSER_LABELS.get(n, n) for n, v in names.items() if v is None]
        risks.append(_risk("warn", "Name not found by every parser",
                           "Missing in: " + ", ".join(missing) + ". Put your name alone on the first line."))

    cid = len(re.findall(r"\(cid:\d+\)", text))
    if cid:
        risks.append(_risk("info", f"{cid} unmappable glyphs",
                           "Characters the PDF does not map to text, usually bullets or icons. Harmless unless "
                           "a list relies on them as separators."))
    if path.suffix.lower() == ".pdf":
        import pdfplumber

        visible = extract_text(path, drop_invisible=True)
        hidden = len(re.sub(r"\s", "", text)) - len(re.sub(r"\s", "", visible))
        if hidden > 0:
            risks.append(_risk("bad", "Hidden text found",
                               f"{hidden} characters of white or tiny text. Recruiters treat this as keyword "
                               "stuffing, and some parsers strip it."))
        else:
            risks.append(_risk("ok", "No hidden text", "Nothing white or tiny that a reviewer could not see."))
        with pdfplumber.open(str(path)) as pdf:
            pages = len(pdf.pages)
            cols = [i + 1 for i, pg in enumerate(pdf.pages) if find_gutter(pg.extract_words(), pg.width)]
            tables = [i + 1 for i, pg in enumerate(pdf.pages) if pg.find_tables()]
        if cols:
            risks.append(_risk("warn", "Two-column layout",
                               f"Detected on page(s) {', '.join(map(str, cols))}. Text-order parsers interleave "
                               "the columns."))
        else:
            risks.append(_risk("ok", "Single-column reading order", "Every parser reads the text in the same order."))
        if tables:
            risks.append(_risk("warn", "Ruled tables",
                               f"On page(s) {', '.join(map(str, tables))}. Text-order parsers merge table labels "
                               "with their content."))
        if pages > 2:
            risks.append(_risk("info", f"{pages} pages", "Parsers handle it; recruiters may not read it all."))
    return risks


def accuracy(gold: dict, parsed: dict[str, ParsedResume]) -> dict:
    out = {}
    for n, r in parsed.items():
        counts = score_resume_lenient(gold, r)
        attempted = ATTEMPTED.get(n) or set(LENIENT_FIELDS)
        out[n] = {
            "f1": micro([counts], [f for f in LENIENT_FIELDS if f in attempted]).f1,
            "fields": {f: (None if f not in attempted else {"tp": c.tp, "fp": c.fp, "fn": c.fn})
                       for f, c in counts.items()},
        }
    return out


# ------------------------------------------------------------------ postings

def load_posting_file(path: str | Path) -> JobPosting:
    """A posting from .json (data/jobs format) or plain text (no knockout rules)."""
    path = Path(path)
    if path.suffix == ".json":
        return load_job(path)
    return posting_from_text(path.read_text(), path.stem)


def posting_from_text(text: str, posting_id: str = "pasted") -> JobPosting:
    title = next((l.strip() for l in text.splitlines() if l.strip()), "Pasted posting")[:80]
    return JobPosting(id=posting_id, title=title, text=text, knockouts=Knockouts())


def default_postings() -> list[JobPosting]:
    return load_jobs(DATA_DIR / "jobs") + load_jobs(DATA_DIR / "jobs_extra")


class Analyzer:
    """Holds fitted scorers and a ranking pool so repeated analyses are fast."""

    def __init__(self, postings: list[JobPosting] | None = None, public_pool: str | Path | bool | None = None,
                 public_per_category: int = 50, use_embedding: bool = True, extra_scorers: list | None = None):
        """`public_pool`: a resume CSV, None to use data/kaggle/Resume.csv when it
        exists, or False for synthetic resumes only."""
        self.postings = postings or default_postings()
        self.pool: dict[str, str] = {}
        for p in load_personas():
            rp = resume_path(p["id"], "single", "pdf", RESUME_DIR)
            if not rp.exists():
                render(p, "single", "pdf", rp, RenderOptions())
            self.pool[p["id"]] = parse_resume(rp).raw_text
        self.n_synthetic = len(self.pool)
        public = None if public_pool is False else (
            Path(public_pool) if public_pool else DATA_DIR / "kaggle" / "Resume.csv")
        if public is not None and public.exists():
            self.pool.update(dict(load_kaggle_resumes(public, limit=public_per_category, category=PUBLIC_CATEGORIES)))
        corpus = list(self.pool.values()) + [j.text for j in self.postings]
        self.scorers = [KeywordScorer().fit(corpus), TfidfScorer().fit(corpus)]
        if use_embedding:
            self.scorers.append(EmbeddingScorer().fit(corpus))
        self.scorers += [x.fit(corpus) for x in extra_scorers or []]
        self._pool_scores: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    @property
    def embedding_backend(self) -> str | None:
        return next((s.backend for s in self.scorers if s.name == "embedding"), None)

    def warm(self, cache_dir: str | Path | None = None) -> None:
        """Precompute pool scores for every posting. Embeddings are cached on
        disk, so only the first launch pays for encoding the pool."""
        emb = next((s for s in self.scorers if s.name == "embedding"), None)
        cache = Path(cache_dir or DATA_DIR.parent / "results" / "_tmp") / "embedding_cache.npz"
        if emb is not None:
            emb.load_cache(cache)
        n_before = len(emb._cache) if emb is not None else 0
        for job in self.postings:
            a = analyze_job(job)
            for s in self.scorers:
                self.pool_scores(s, a)
        if emb is not None and len(emb._cache) > n_before:
            emb.save_cache(cache)

    def pool_scores(self, scorer, analysis) -> list[float]:
        key = (scorer.name, analysis.job.id + str(hash(analysis.job.text)))
        with self._lock:
            if key not in self._pool_scores:
                self._pool_scores[key] = [scorer.score(t, analysis) for t in self.pool.values()]
            return self._pool_scores[key]

    def match(self, text: str, parsed: dict[str, ParsedResume], job: JobPosting, application: dict) -> dict:
        a = analyze_job(job)
        knockouts = {}
        for pname in ("naive", best_parse(parsed)):
            if pname in parsed:
                ko = apply_knockouts(parsed[pname], job.knockouts, application)
                knockouts[pname] = {"status": ko.status, "reasons": ko.reasons, "missing": ko.missing}
        scores = []
        for s in self.scorers:
            mine = s.score(text, a)
            others = self.pool_scores(s, a)
            scores.append({
                "name": s.name, "score": mine, "rank": 1 + sum(o > mine + 1e-12 for o in others),
                "of": len(others) + 1, "best_other": max(others) if others else None,
                "median_other": sorted(others)[len(others) // 2] if others else None,
                "backend": getattr(s, "backend", None),
            })
        kw = self.scorers[0].explain(text, a)
        return {
            "posting": {"id": job.id, "title": job.title, "has_knockouts": job.knockouts != Knockouts()},
            "knockouts": knockouts, "scores": scores, "matched": kw.matched, "missing": kw.missing,
            "requirements": [{"term": r.surface, "level": r.level, "curated": r.curated} for r in a.requirements],
        }

    def analyze(self, path: str | Path, postings: list[JobPosting] | None = None, application: dict | None = None,
                gold: dict | None = None, use_engines: bool = True, with_skillner: bool = True) -> dict:
        """`with_skillner` adds SkillNer's skill list (accurate but slow: about a
        minute for a two-page resume the first time)."""
        path = Path(path)
        parsed = parse_all(path, use_engines=use_engines)
        text = parsed["naive"].raw_text
        best = best_parse(parsed)
        skills = {"curated": sorted(default_taxonomy().find_all(text))}
        if with_skillner and skillner_available():
            try:
                skills["skillner"] = sorted(skillner_skills(text))
            except Exception:
                pass
        application = application or {}
        result = {
            "file": path.name,
            "parsers": {n: fields_of(r) for n, r in parsed.items()},
            "parser_labels": {n: PARSER_LABELS.get(n, n) for n in parsed},
            "best": best,
            "agreement": agreement(parsed),
            "risks": diagnose(path, parsed),
            "skills": skills,
            "matches": [self.match(text, parsed, j, application) for j in (postings or self.postings)],
            "raw_text": text,
            "pool": {"size": len(self.pool), "synthetic": self.n_synthetic,
                     "public": len(self.pool) - self.n_synthetic},
        }
        if gold:
            result["accuracy"] = accuracy(gold, parsed)
        return result
