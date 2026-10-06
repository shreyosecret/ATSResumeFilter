"""End-to-end screening: parse -> knockout -> score -> rank."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .data import load_personas, resume_path
from .jd import analyze_job
from .knockout import REJECT, KnockoutResult, apply_knockouts
from .models import JobAnalysis, JobPosting, ParsedResume
from .parser import parse_resume, parse_text


@dataclass
class Candidate:
    id: str
    parsed: ParsedResume
    application: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.parsed.raw_text


def candidates_from_personas(layout: str = "single", fmt: str = "pdf", personas: list[dict] | None = None,
                             root: Path | None = None) -> list[Candidate]:
    personas = personas or load_personas()
    out = []
    for p in personas:
        path = resume_path(p["id"], layout, fmt, root) if root else resume_path(p["id"], layout, fmt)
        out.append(Candidate(p["id"], parse_resume(path), p.get("application", {})))
    return out


def candidates_from_texts(texts: list[tuple[str, str]]) -> list[Candidate]:
    """Plain-text candidates (e.g. Kaggle resumes). No application answers, so
    work-authorization rules are skipped for them."""
    return [Candidate(i, parse_text(t, source=i)) for i, t in texts]


def rank_scores(scores: pd.Series, eligible: pd.Series) -> pd.Series:
    """1 = best among eligible candidates; ineligible candidates get NaN."""
    r = scores.where(eligible).rank(ascending=False, method="min")
    return r


def screen(candidates: list[Candidate], job: JobPosting | JobAnalysis, scorers: list,
           primary: str | None = None, missing_policy: str = "review") -> pd.DataFrame:
    analysis = job if isinstance(job, JobAnalysis) else analyze_job(job)
    rows = []
    for c in candidates:
        ko: KnockoutResult = apply_knockouts(c.parsed, analysis.job.knockouts, c.application, missing_policy)
        row = {
            "id": c.id,
            "name": c.parsed.name,
            "knockout": ko.status,
            "knockout_reasons": "; ".join(ko.reasons),
            "missing_fields": ", ".join(ko.missing),
        }
        for s in scorers:
            row[s.name] = round(s.score(c.text, analysis), 4)
        rows.append(row)
    df = pd.DataFrame(rows)
    eligible = df["knockout"] != REJECT
    for s in scorers:
        df[f"rank_{s.name}"] = rank_scores(df[s.name], eligible)
    primary = primary or scorers[0].name
    df = df.sort_values([f"rank_{primary}", "id"], na_position="last").reset_index(drop=True)
    return df
