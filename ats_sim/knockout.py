"""Rule-based knockout filter.

In real systems knockouts are usually application-form questions ("Are you
authorized to work in the US?", "What is your GPA?"). Many forms are
pre-filled from the parsed resume, and a candidate who does not correct the
autofill is screened on what the parser extracted. This module models that:
education rules read the parsed fields by default, while work authorization
always comes from the candidate's application answers, because a parser
cannot know it.

Each rule yields PASS, REJECT, or MISSING. What MISSING means is a policy
choice (`missing_policy`): send to human review (default), reject, or pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Knockouts, ParsedResume
from .parser import DEGREE_RANK

PASS, REJECT, REVIEW = "PASS", "REJECT", "REVIEW"


@dataclass
class KnockoutResult:
    status: str  # PASS | REJECT | REVIEW
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == PASS


def _field_matches(field_of_study: str, accepted: list[str]) -> bool:
    f = field_of_study.lower()
    return any(a.lower() in f or f in a.lower() for a in accepted)


_LEVEL_NAMES = {"BA": "Bachelor's", "BS": "Bachelor's", "MS": "Master's", "PHD": "Ph.D."}


def check_rules(resume: ParsedResume, rules: Knockouts, application: dict | None = None,
                found: list | None = None) -> list[dict]:
    """One row per rule, for showing a candidate why they pass or fail:
    {"rule", "requirement", "resume", "status"} with status pass, fail,
    missing (the parser could not read it), ask (a form question the resume
    cannot answer) or info (shown but not enforced)."""
    application = application or {}
    rows = []
    if rules.min_degree_level:
        lvl = resume.degree_level
        ok = lvl is not None and DEGREE_RANK[lvl] >= DEGREE_RANK[rules.min_degree_level]
        rows.append({"rule": "Degree", "requirement": f"{_LEVEL_NAMES[rules.min_degree_level]} or higher",
                     "resume": _LEVEL_NAMES.get(lvl) if lvl else None,
                     "status": "missing" if lvl is None else "pass" if ok else "fail"})
    if rules.degree_fields:
        f = resume.field_of_study
        rows.append({"rule": "Field of study", "requirement": ", ".join(rules.degree_fields), "resume": f,
                     "status": "missing" if f is None else "pass" if _field_matches(f, rules.degree_fields) else "fail"})
    for item in found or []:
        if item.get("rule") == "field" and not item.get("enforced"):
            rows.append({"rule": "Field of study", "requirement": item["value"], "resume": resume.field_of_study,
                         "status": "info"})
    if rules.min_gpa is not None:
        g = resume.gpa
        rows.append({"rule": "GPA", "requirement": f"{rules.min_gpa:.2f} or higher",
                     "resume": None if g is None else f"{g:.2f}",
                     "status": "missing" if g is None else "pass" if g >= rules.min_gpa else "fail"})
    if rules.grad_window:
        lo, hi = rules.grad_window
        d = resume.grad_date
        rows.append({"rule": "Graduation", "requirement": f"by {hi}" if lo <= "1900-12" else f"{lo} to {hi}",
                     "resume": d, "status": "missing" if d is None else "pass" if lo <= d <= hi else "fail"})
    if rules.require_work_authorization:
        a = application.get("work_authorized")
        rows.append({"rule": "Work authorization", "requirement": "Authorized to work", "resume": None,
                     "status": "ask" if a is None else "pass" if a else "fail"})
    if rules.no_sponsorship:
        n = application.get("needs_sponsorship")
        rows.append({"rule": "Visa sponsorship", "requirement": "Not offered", "resume": None,
                     "status": "ask" if n is None else "fail" if n else "pass"})
    return rows


def apply_knockouts(
    resume: ParsedResume,
    rules: Knockouts,
    application: dict | None = None,
    missing_policy: str = "review",
) -> KnockoutResult:
    application = application or {}
    reasons: list[str] = []
    missing: list[str] = []

    if rules.grad_window:
        lo, hi = rules.grad_window
        if resume.grad_date is None:
            missing.append("graduation date")
        elif not (lo <= resume.grad_date <= hi):
            reasons.append(f"graduation date {resume.grad_date} outside {lo}..{hi}")

    if rules.min_gpa is not None:
        if resume.gpa is None:
            missing.append("GPA")
        elif resume.gpa < rules.min_gpa:
            reasons.append(f"GPA {resume.gpa:.2f} below {rules.min_gpa:.2f}")

    if rules.min_degree_level:
        if resume.degree_level is None:
            missing.append("degree")
        elif DEGREE_RANK[resume.degree_level] < DEGREE_RANK[rules.min_degree_level]:
            reasons.append(f"degree {resume.degree_level} below {rules.min_degree_level}")

    if rules.degree_fields:
        if resume.field_of_study is None:
            missing.append("field of study")
        elif not _field_matches(resume.field_of_study, rules.degree_fields):
            reasons.append(f"field of study '{resume.field_of_study}' not in accepted list")

    if rules.require_work_authorization and application.get("work_authorized") is False:
        reasons.append("not authorized to work")
    if rules.no_sponsorship and application.get("needs_sponsorship"):
        reasons.append("requires visa sponsorship")

    if reasons:
        return KnockoutResult(REJECT, reasons, missing)
    if missing:
        if missing_policy == "reject":
            return KnockoutResult(REJECT, [f"missing {m}" for m in missing], missing)
        if missing_policy == "review":
            return KnockoutResult(REVIEW, [], missing)
    return KnockoutResult(PASS, [], missing)
