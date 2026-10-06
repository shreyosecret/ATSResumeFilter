"""Adapters for open-source parsing and skill-extraction engines.

Each third-party engine is installed and run separately; no third-party code
is stored in this repo. `scripts/setup_external.sh` installs them.

  OpenResume   (AGPL-3.0, TypeScript) https://github.com/xitanggg/open-resume
               Browser-based resume builder whose parser students use to check
               "ATS readability". Run under Node by external/openresume/run.mjs.
               Needs OPENRESUME_DIR (a checkout) and `npm install` in that folder.
  pyresparser  (GPL-3.0, Python) https://github.com/OmkarPathak/pyresparser
               The most widely used Python resume parser; needs spaCy 2, so it
               runs in its own Python 3.8 environment via external/pyresparser/run.py.
               Needs PYRESPARSER_PYTHON (that environment's python).
  SkillNer     (MIT, Python) https://github.com/AnasAito/SkillNER
               Skill extraction against the EMSI/Lightcast open skills database
               (about 31,000 skills). Imported directly when installed.

Every adapter maps the engine's output into a ParsedResume using this
project's own normalizers (degree and date regexes), so all engines are
scored by the same rules. Fields an engine does not attempt stay empty and
are reported as not attempted rather than counted as failures.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from .models import ExperienceEntry, ParsedResume
from .parser import _all_dates, extract_degree, extract_skill_items

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = ROOT / "external"


def _run_jsonl(cmd: list[str], files: list[str], env: dict | None = None, batch: int = 64,
               timeout: int = 3600) -> dict[str, dict]:
    """Run an engine on files in batches; collect {file: json} from stdout lines."""
    out: dict[str, dict] = {}
    for i in range(0, len(files), batch):
        chunk = [str(f) for f in files[i:i + batch]]
        proc = subprocess.run(cmd + chunk, capture_output=True, text=True, env=env, timeout=timeout)
        for line in proc.stdout.splitlines():
            if line.startswith("{"):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out[rec["file"]] = rec
        missing = [f for f in chunk if f not in out]
        if missing and proc.returncode != 0:
            raise RuntimeError(f"{cmd[0]} failed: {proc.stderr[-2000:]}")
    return out


def _degree_fields(degree_text: str | None) -> tuple[str | None, str | None]:
    if not degree_text:
        return None, None
    return extract_degree(degree_text)


def _grad(date_text: str | None) -> str | None:
    dates = _all_dates(date_text or "")
    return max(dates) if dates else None


def _join_lines(lines: list[str]) -> str:
    """Join skills-section lines: a line continues the previous one when that
    line ends with a comma or this one starts lowercase (a wrapped item);
    otherwise it starts a new item."""
    out = ""
    for line in (l.strip() for l in lines):
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith(",") or line[:1].islower():
            out += " " + line
        else:
            out += ", " + line
    return out


def _gpa(value) -> float | None:
    m = re.search(r"[0-4]\.\d{1,2}", str(value or ""))
    return float(m.group(0)) if m else None


# ------------------------------------------------------------------ OpenResume

class OpenResumeParser:
    name = "openresume"
    formats = ("pdf",)

    def __init__(self, openresume_dir: str | None = None):
        self.dir = openresume_dir or os.environ.get("OPENRESUME_DIR")
        self.runner = EXTERNAL / "openresume" / "run.mjs"

    def available(self) -> bool:
        return bool(self.dir and Path(self.dir, "src").exists() and shutil.which("node")
                    and (EXTERNAL / "openresume" / "node_modules" / "pdfjs-dist").exists())

    def raw_many(self, paths: list[str | Path]) -> dict[str, dict]:
        env = dict(os.environ, OPENRESUME_DIR=str(self.dir))
        return _run_jsonl(["node", str(self.runner)], [str(p) for p in paths], env=env)

    def parse_many(self, paths: list[str | Path]) -> dict[str, ParsedResume]:
        return {f: self.convert(rec.get("resume"), f) for f, rec in self.raw_many(paths).items()}

    @staticmethod
    def convert(r: dict | None, source: str) -> ParsedResume:
        if not r:
            return ParsedResume(source=source, raw_text="")
        prof = r.get("profile", {})
        edu = (r.get("educations") or [{}])[0]
        level, field = _degree_fields(edu.get("degree"))
        skills_text = _join_lines(r.get("skills", {}).get("descriptions", []))
        featured = [s["skill"] for s in r.get("skills", {}).get("featuredSkills", []) if s.get("skill")]
        return ParsedResume(
            source=source, raw_text=json.dumps(r),
            name=prof.get("name") or None, email=prof.get("email") or None, phone=prof.get("phone") or None,
            degree_level=level, field_of_study=field, school=edu.get("school") or None,
            grad_date=_grad(edu.get("date")), gpa=_gpa(edu.get("gpa")),
            skills=featured + extract_skill_items(skills_text),
            experience=[ExperienceEntry(title=w.get("jobTitle") or None, company=w.get("company") or None,
                                        dates=w.get("date") or None) for w in r.get("workExperiences", [])],
        )


# ------------------------------------------------------------------ pyresparser

class PyresparserParser:
    name = "pyresparser"
    formats = ("pdf", "docx")

    def __init__(self, python: str | None = None):
        self.python = python or os.environ.get("PYRESPARSER_PYTHON")
        self.runner = EXTERNAL / "pyresparser" / "run.py"

    def available(self) -> bool:
        return bool(self.python and Path(self.python).exists())

    def raw_many(self, paths: list[str | Path]) -> dict[str, dict]:
        return _run_jsonl([self.python, str(self.runner)], [str(p) for p in paths])

    def parse_many(self, paths: list[str | Path]) -> dict[str, ParsedResume]:
        return {f: self.convert(rec.get("resume"), f) for f, rec in self.raw_many(paths).items()}

    @staticmethod
    def convert(r: dict | None, source: str) -> ParsedResume:
        if not r:
            return ParsedResume(source=source, raw_text="")
        level, field = _degree_fields(" ".join(r.get("degree") or []))
        titles = r.get("designation") or []
        companies = r.get("company_names") or []
        exp = [ExperienceEntry(title=t, company=companies[i] if i < len(companies) else None)
               for i, t in enumerate(titles)]
        return ParsedResume(
            source=source, raw_text=json.dumps(r),
            name=r.get("name"), email=r.get("email"), phone=r.get("mobile_number"),
            degree_level=level, field_of_study=field, school=r.get("college_name"),
            grad_date=None, gpa=None,  # not attempted by pyresparser
            skills=list(r.get("skills") or []), experience=exp,
        )


ATTEMPTED = {
    "naive": None, "layout_aware": None,  # None = every field
    "openresume": None,
    "pyresparser": {"name", "email", "phone", "degree_level", "field_of_study", "school", "skills",
                    "experience", "job_titles"},
}


# ------------------------------------------------------------------ SkillNer

@lru_cache(maxsize=1)
def _skillner():
    import warnings

    import spacy
    from spacy.matcher import PhraseMatcher

    warnings.filterwarnings("ignore")
    from skillNer.general_params import SKILL_DB
    from skillNer.skill_extractor_class import SkillExtractor

    for model in ("en_core_web_lg", "en_core_web_md", "en_core_web_sm"):
        try:
            nlp = spacy.load(model)
            break
        except OSError:
            continue
    else:
        raise OSError("SkillNer needs a spaCy English model: python -m spacy download en_core_web_lg")
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):  # it prints progress while building matchers
        ext = SkillExtractor(nlp, SKILL_DB, PhraseMatcher)
    return ext, SKILL_DB


def skillner_available() -> bool:
    try:
        import skillNer  # noqa: F401
        import IPython  # noqa: F401  (undeclared SkillNer dependency)
    except ImportError:
        return False
    return True


def clean_skill_name(name: str) -> str:
    """'Python (Programming Language)' -> 'Python'."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


@lru_cache(maxsize=4096)
def skillner_skills(text: str, include_ngram: bool = True) -> frozenset[str]:
    """EMSI/Lightcast skill names found in text by SkillNer (parentheticals removed)."""
    ext, db = _skillner()
    text = re.sub(r"\s+", " ", text)
    if not text.strip():
        return frozenset()
    try:
        ann = ext.annotate(text)
    except Exception:  # SkillNer raises on some inputs (e.g. no tokens after cleaning)
        return frozenset()
    keys = ["full_matches"] + (["ngram_scored"] if include_ngram else [])
    return frozenset(clean_skill_name(db[m["skill_id"]]["skill_name"]) for k in keys for m in ann["results"][k])


class SkillNerScorer:
    """Share of the posting's SkillNer skills that SkillNer also finds in the
    resume. Uses the 31k-skill EMSI/Lightcast taxonomy instead of this
    project's 64-skill curated list, and its own normalization of surface
    forms. Presence-based, like the keyword scorer."""

    name = "skillner"

    def fit(self, corpus: list[str]) -> "SkillNerScorer":
        return self

    def _job_skills(self, analysis) -> frozenset[str]:
        text = "\n".join(analysis.requirement_lines) or analysis.job.text
        return skillner_skills(text)

    def score(self, text: str, analysis) -> float:
        want = self._job_skills(analysis)
        if not want:
            return 0.0
        return len(want & skillner_skills(text)) / len(want)

    def explain(self, text: str, analysis):
        from .scorers import ScoreDetail

        want, have = self._job_skills(analysis), skillner_skills(text)
        return ScoreDetail(self.score(text, analysis), sorted(want & have), sorted(want - have))


def available_parsers() -> list:
    return [p for p in (OpenResumeParser(), PyresparserParser()) if p.available()]


# ------------------------------------------------------------------ ensemble

def _norm_key(field: str, value):
    from .evaluate import _norm, _norm_gpa, _norm_phone, _tokens

    if value is None:
        return None
    if field == "phone":
        return _norm_phone(value)
    if field == "gpa":
        return _norm_gpa(value)
    if field in ("degree_level", "grad_date"):
        return value
    if field == "email":
        return _norm(value)
    return " ".join(_tokens(value)) or None


def vote(results: list[ParsedResume], names: list[str]) -> ParsedResume:
    """Field-by-field majority vote across engines.

    Scalars: the normalized value proposed by the most engines wins; ties go
    to the earlier engine in `names` (put the most trusted first). A field
    only one engine filled is kept. List fields (skills, experience): items
    proposed by at least two engines are kept, plus every item from the first
    engine that has any, so one noisy engine cannot add items on its own.
    This is a generic rule, but it was written after seeing the parser
    benchmark, so its benchmark score is not a held-out result.
    """
    from .evaluate import _close, _tokens

    out = ParsedResume(source=results[0].source if results else "", raw_text=results[0].raw_text if results else "")
    for field in ("name", "email", "phone", "degree_level", "field_of_study", "school", "grad_date", "gpa"):
        tally: dict = {}
        for rank, r in enumerate(results):
            v = getattr(r, field)
            k = _norm_key(field, v)
            if k is None:
                continue
            count, first_rank, first_value = tally.get(k, (0, rank, v))
            tally[k] = (count + 1, min(first_rank, rank), first_value)
        if tally:
            best = max(tally.values(), key=lambda t: (t[0], -t[1]))
            setattr(out, field, best[2])

    def merge(lists: list[list], same) -> list:
        base_idx = next((i for i, lst in enumerate(lists) if lst), None)
        if base_idx is None:
            return []
        kept = list(lists[base_idx])
        for i, lst in enumerate(lists):
            if i == base_idx:
                continue
            for item in lst:
                if any(same(item, k) for k in kept):
                    continue
                support = sum(1 for j, other in enumerate(lists) if j != i and any(same(item, o) for o in other))
                if support >= 1:
                    kept.append(item)
        return kept

    out.skills = merge([r.skills for r in results], lambda a, b: _close(a, b) or _close(b, a))

    def same_entry(a: ExperienceEntry, b: ExperienceEntry) -> bool:
        ta = set(_tokens(a.title or a.company))
        tb = set(_tokens(b.title or b.company))
        return bool(ta and tb) and (ta <= tb or tb <= ta)

    out.experience = merge([r.experience for r in results], same_entry)
    return out
