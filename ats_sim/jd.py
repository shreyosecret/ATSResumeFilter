"""Job description analyzer: required vs preferred skills from a posting."""
from __future__ import annotations

import json
import re
import warnings
from functools import lru_cache
from pathlib import Path

from .models import JobAnalysis, JobPosting, Knockouts, SkillRequirement
from .skills import SkillTaxonomy, default_taxonomy, term_pattern

JD_HEADINGS = {
    "required": {
        "required qualifications", "requirements", "minimum qualifications", "basic qualifications",
        "qualifications", "what you need", "must have", "must haves", "required skills",
    },
    "preferred": {
        "preferred qualifications", "preferred", "nice to have", "nice to haves", "bonus",
        "bonus points", "pluses", "preferred skills",
    },
    "responsibilities": {"responsibilities", "what you'll do", "what you will do", "duties"},
    "about": {"about the role", "about us", "about the team", "overview"},
}
_JD_LOOKUP = {h: s for s, hs in JD_HEADINGS.items() for h in hs}
DEGREE_LINE = re.compile(r"\b(B\.\s?S\.|M\.\s?S\.|B\.\s?A\.|Ph\.?\s?D|degree|graduat\w*|GPA|authori[sz]\w*|sponsor\w*)",
                         re.IGNORECASE)  # lines that state screening rules, not skills
ALTERNATIVE_SEP = re.compile(r"^\s*,?\s*(?:or|/)\s*$", re.IGNORECASE)
PREFERRED_CUES = re.compile(r"\b(ideally|preferred|a plus|nice to have|bonus|desirable)\b", re.IGNORECASE)

GENERIC_HEADS = {
    "experience", "knowledge", "skill", "skills", "familiarity", "proficiency", "field", "degree",
    "coursework", "project", "projects", "role", "team", "candidate", "candidates", "ability",
    "exposure", "year", "years", "environment", "work", "authorization", "understanding", "background",
    "program", "programming", "qualification", "qualifications", "states", "united states", "visa",
    "internship", "who", "you", "we", "it", "they", "that", "this", "which",
}
STRIP_MODIFIERS = {"strong", "working", "hands-on", "solid", "excellent", "good", "related", "basic", "proven"}


def load_job(path: str | Path) -> JobPosting:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    k = raw.get("knockouts", {})
    knockouts = Knockouts(
        grad_window=tuple(k["grad_window"]) if k.get("grad_window") else None,
        min_gpa=k.get("min_gpa"),
        degree_fields=k.get("degree_fields"),
        min_degree_level=k.get("min_degree_level"),
        require_work_authorization=k.get("require_work_authorization", False),
        no_sponsorship=k.get("no_sponsorship", False),
    )
    return JobPosting(id=raw["id"], title=raw["title"], text=raw["text"], knockouts=knockouts)


def load_jobs(directory: str | Path | None = None) -> list[JobPosting]:
    directory = Path(directory) if directory else Path(__file__).resolve().parent.parent / "data" / "jobs"
    return [load_job(p) for p in sorted(directory.glob("*.json"))]


def split_jd_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"intro": []}
    current = "intro"
    for line in text.splitlines():
        key = _JD_LOOKUP.get(line.strip().lower().rstrip(":"))
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


@lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy

        return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    except (ImportError, OSError):
        warnings.warn(
            "spaCy model en_core_web_sm not available; noun-phrase extraction is disabled. "
            "Run: python -m spacy download en_core_web_sm"
        )
        return None


def _line_levels(sections: dict[str, str]) -> list[tuple[str, str]]:
    """(line, default level) for every line that can carry a skill."""
    out = []
    # Degree and graduation lines feed the knockout rules, not the skill list.
    for sec, level in (("required", "required"), ("preferred", "preferred"), ("responsibilities", "preferred")):
        for line in sections.get(sec, "").splitlines():
            if line.strip() and not DEGREE_LINE.search(line):
                out.append((line.strip(" -•\t"), level))
    return out


def noun_phrase_terms(lines: list[tuple[str, str]], known: set[str]) -> list[SkillRequirement]:
    nlp = _nlp()
    if nlp is None:
        return []
    terms: dict[str, SkillRequirement] = {}
    for line, level in lines:
        for chunk in nlp(line).noun_chunks:
            tokens = [t for t in chunk if t.pos_ not in {"DET", "PRON", "NUM", "PUNCT", "CCONJ"}]
            # Bullets usually open with an imperative verb that the tagger
            # mislabels as a noun ("Build prototypes"); drop it.
            if tokens and tokens[0].i == 0:
                tokens = tokens[1:]
            while tokens and tokens[0].text.lower() in STRIP_MODIFIERS:
                tokens = tokens[1:]
            if not tokens or tokens[-1].text.lower() in GENERIC_HEADS:
                continue
            phrase = " ".join(t.text for t in tokens)
            low = phrase.lower()
            if len(tokens) > 3 or len(low) < 3 or any(ch.isdigit() for ch in low):
                continue
            if len(tokens) == 1 and not phrase.isupper():
                continue  # single common nouns ("data", "analysis") are too vague to be skills
            if any(term_pattern(k).search(phrase) for k in known):
                continue
            if low not in terms or (level == "required" and terms[low].level != "required"):
                terms[low] = SkillRequirement(name=low, surface=phrase, level=level, curated=False)
    return list(terms.values())


def analyze_job(job: JobPosting, taxonomy: SkillTaxonomy | None = None, use_noun_phrases: bool = True) -> JobAnalysis:
    taxonomy = taxonomy or default_taxonomy()
    sections = split_jd_sections(job.text)
    lines = _line_levels(sections)

    found: dict[str, SkillRequirement] = {}
    n_groups = 0
    for line, level in lines:
        cue = PREFERRED_CUES.search(line)
        hits = []  # (start, end, skill name, surface)
        for skill in taxonomy.skills:
            for form in skill.surface_forms:
                m = term_pattern(form).search(line)
                if m:
                    hits.append((m.start(), m.end(), skill.name, m.group(0)))
                    break
        hits.sort()
        groups: dict[str, str] = {}
        for a, b in zip(hits, hits[1:]):
            if ALTERNATIVE_SEP.match(line[a[1]: b[0]]):
                gid = groups.get(a[2])
                if gid is None:
                    n_groups += 1
                    gid = groups[a[2]] = f"{job.id}-alt{n_groups}"
                groups[b[2]] = gid
        for start, _, name, surface in hits:
            lvl = "preferred" if cue and start > cue.start() else level
            prev = found.get(name)
            if prev is None or (lvl == "required" and prev.level != "required"):
                found[name] = SkillRequirement(name=name, surface=surface, level=lvl, group=groups.get(name))

    requirements = list(found.values())
    if use_noun_phrases:
        known = {f for s in taxonomy.skills for f in s.surface_forms}
        requirements += noun_phrase_terms(lines, known)
    req_lines = [l for l, _ in lines]
    return JobAnalysis(job=job, requirements=requirements, sections=sections, requirement_lines=req_lines)
