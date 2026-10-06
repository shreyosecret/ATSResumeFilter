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


# ----------------------------------------------------------------- lenient mode
#
# Used to compare different parsers fairly. Engines format fields differently
# (one keeps ", Raleigh, NC" after the school name, another returns job titles
# without companies), so strict string equality would mostly measure
# formatting. Lenient matching credits a field when the gold tokens are all
# present and little else is.

LENIENT_FIELDS = ALL_FIELDS + ("job_titles",)
_MAX_EXTRA_TOKENS = 3


def _tokens(s) -> list[str]:
    s = re.sub(r"\([^)]*\)", " ", str(s or "").lower())
    return re.findall(r"[a-z0-9+#&]+", s)


def _close(gold, pred) -> bool:
    g, p = _tokens(gold), _tokens(pred)
    if not g or not p:
        return False
    return set(g) <= set(p) and len(p) - len(g) <= _MAX_EXTRA_TOKENS


def _match_sets(gold: list[str], pred: list[str], close=_close) -> Counts:
    """Greedy one-to-one matching of gold items to predicted items."""
    unused = list(pred)
    tp = 0
    for g in gold:
        for i, p in enumerate(unused):
            if close(g, p):
                tp += 1
                del unused[i]
                break
    return Counts(tp=tp, fp=len(unused), fn=len(gold) - tp)


def _scalar(gold, pred, close) -> Counts:
    if gold is None and pred is None:
        return Counts()
    if gold is None:
        return Counts(fp=1)
    if pred is None:
        return Counts(fn=1)
    return Counts(tp=1) if close(gold, pred) else Counts(fp=1, fn=1)


def score_resume_lenient(persona: dict, parsed: ParsedResume) -> dict[str, Counts]:
    e = persona["education"]
    exact = lambda a, b: a == b  # noqa: E731
    entries = [" ".join(filter(None, (x.title, x.company))) for x in parsed.experience]
    titles = [x.title or x.company for x in parsed.experience if (x.title or x.company)]

    def entry_close(gold_pair, pred_text):
        title, company = gold_pair
        return set(_tokens(title)) | set(_tokens(company)) <= set(_tokens(pred_text))

    return {
        "name": _scalar(persona["name"], parsed.name, _close),
        "email": _scalar(_norm(persona["email"]), _norm(parsed.email), exact),
        "phone": _scalar(_norm_phone(persona["phone"]), _norm_phone(parsed.phone), exact),
        "degree_level": _scalar(e["degree_level"], parsed.degree_level, exact),
        "field_of_study": _scalar(e["field"], parsed.field_of_study, _close),
        "school": _scalar(e["school"], parsed.school, _close),
        "grad_date": _scalar(e["grad_date"], parsed.grad_date, exact),
        "gpa": _scalar(_norm_gpa(e.get("gpa")), _norm_gpa(parsed.gpa), exact),
        "skills": _match_sets(persona["skills"], [s for s in parsed.skills if s.strip()]),
        "experience": _match_sets([(x["title"], x["company"]) for x in persona["experience"]], entries,
                                  close=entry_close),
        "job_titles": _match_sets([x["title"] for x in persona["experience"]], titles,
                                  close=lambda g, p: _close(g, p) or set(_tokens(g)) <= set(_tokens(p))),
    }
