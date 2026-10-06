"""Field-extraction accuracy against the persona answer key."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ParsedResume

SCALAR_FIELDS = ("name", "email", "phone", "degree_level", "field_of_study", "school", "grad_date", "gpa")
LIST_FIELDS = ("skills", "experience")
ALL_FIELDS = SCALAR_FIELDS + LIST_FIELDS


def _norm(s) -> str | None:
    if s is None:
        return None
    s = re.sub(r"[^\w+#&@.]+", " ", str(s).lower()).strip()
    return s or None


def _norm_phone(s) -> str | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return digits[-10:] or None


def _norm_gpa(g) -> str | None:
    return None if g is None else f"{float(g):.2f}"


def gold_fields(p: dict) -> dict:
    e = p["education"]
    return {
        "name": _norm(p["name"]),
        "email": _norm(p["email"]),
        "phone": _norm_phone(p["phone"]),
        "degree_level": e["degree_level"],
        "field_of_study": _norm(e["field"]),
        "school": _norm(e["school"]),
        "grad_date": e["grad_date"],
        "gpa": _norm_gpa(e.get("gpa")),
        "skills": {_norm(s) for s in p["skills"]},
        "experience": {f"{_norm(x['title'])} @ {_norm(x['company'])}" for x in p["experience"]},
    }


def predicted_fields(r: ParsedResume) -> dict:
    return {
        "name": _norm(r.name),
        "email": _norm(r.email),
        "phone": _norm_phone(r.phone),
        "degree_level": r.degree_level,
        "field_of_study": _norm(r.field_of_study),
        "school": _norm(r.school),
        "grad_date": r.grad_date,
        "gpa": _norm_gpa(r.gpa),
        "skills": {s for s in (_norm(x) for x in r.skills) if s},
        "experience": {f"{_norm(x.title)} @ {_norm(x.company)}" for x in r.experience},
    }


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def __iadd__(self, other: "Counts") -> "Counts":
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        return self

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def compare_field(gold, pred) -> Counts:
    """Scalar: a wrong value is both a false positive and a false negative.
    Sets: standard set overlap."""
    if isinstance(gold, set):
        pred = pred or set()
        return Counts(tp=len(gold & pred), fp=len(pred - gold), fn=len(gold - pred))
    if gold is None and pred is None:
        return Counts()
    if gold is None:
        return Counts(fp=1)
    if pred is None:
        return Counts(fn=1)
    return Counts(tp=1) if gold == pred else Counts(fp=1, fn=1)


def score_resume(persona: dict, parsed: ParsedResume) -> dict[str, Counts]:
    g, p = gold_fields(persona), predicted_fields(parsed)
    return {f: compare_field(g[f], p[f]) for f in ALL_FIELDS}


def micro(counts: list[dict[str, Counts]], fields=ALL_FIELDS) -> Counts:
    total = Counts()
    for c in counts:
        for f in fields:
            total += c[f]
    return total
