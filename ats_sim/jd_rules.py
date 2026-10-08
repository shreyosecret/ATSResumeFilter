"""Read screening (knockout) rules out of a pasted job description.

Real systems take these from structured application questions that a
recruiter fills in; a pasted posting only has prose. This reads the common
phrasings: degree level and field, minimum GPA, graduation window, work
authorization and visa sponsorship. Each rule comes with the sentence it was
read from, so a person can check it.

It is deliberately conservative: when a posting says "or a related field",
the field list is shown but not enforced, because a human decides what is
related. Anything it cannot read confidently is left out rather than guessed.
"""
from __future__ import annotations

import re

from .models import Knockouts

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_SEASONS = {"spring": 5, "summer": 8, "fall": 12, "autumn": 12, "winter": 12}
_SEASON_SPAN = {"spring": (3, 6), "summer": (6, 8), "fall": (9, 12), "autumn": (9, 12), "winter": (12, 12)}
_WHEN = (r"(?P<{n}m>(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?|spring|summer|fall|autumn|winter)?"
         r"\s*,?\s*(?P<{n}y>(?:19|20)\d\d)")
_GRAD = r"(?:graduat\w*|graduation(?:\s+date)?|complet\w+\s+(?:of\s+)?(?:your|the|their)?\s*degree|degree\s+complet\w+)"
GRAD_BETWEEN = re.compile(_GRAD + r"[^.;\n]{0,40}?\bbetween\s+" + _WHEN.format(n="a") + r"\s+(?:and|to|-|–)\s+"
                          + _WHEN.format(n="b"), re.IGNORECASE)
GRAD_BY = re.compile(_GRAD + r"[^.;\n]{0,30}?\b(?:by|before|no later than|prior to)\s+" + _WHEN.format(n="a"),
                     re.IGNORECASE)
GRAD_IN = re.compile(r"(?:class of\s+(?P<cy>(?:19|20)\d\d)|" + _GRAD + r"[^.;\n]{0,20}?\b(?:in|of)\s+"
                     + _WHEN.format(n="a") + r")", re.IGNORECASE)
GPA_RE = re.compile(
    r"(?:(?:minimum|min\.?|cumulative|overall)\s+)*GPA\s*(?:of\s*)?(?:at least\s*|above\s*|over\s*)?(?P<g1>[0-4]\.\d{1,2})"
    r"|(?P<g2>[0-4]\.\d{1,2})\s*(?:/\s*4\.0+\s*)?(?:cumulative\s+)?GPA",
    re.IGNORECASE)
AUTH_RE = re.compile(r"\b(?:authori[sz]ed|authori[sz]ation|eligible|eligibility)\s+(?:to\s+work|for\s+employment)"
                     r"|\bwork\s+authori[sz]ation\b|\blegally\s+(?:able|allowed)\s+to\s+work", re.IGNORECASE)
NO_SPONSOR_RE = re.compile(
    r"\b(?:unable|not able|will not|won't|cannot|can't|do not|does not|don't|not)\s+(?:to\s+)?(?:\w+\s+){0,2}sponsor"
    r"|\bno\s+(?:visa\s+|immigration\s+)?sponsorship|\bwithout\s+(?:the\s+need\s+for\s+)?(?:current\s+or\s+future\s+)?"
    r"(?:visa\s+|immigration\s+)?sponsorship|\bnot\s+(?:eligible|available)\s+for\s+(?:visa\s+)?sponsorship",
    re.IGNORECASE)
LEVELS = [
    ("PHD", re.compile(r"\b(?:Ph\.?\s?D\.?|doctora(?:te|l)|Doctor of Philosophy)", re.IGNORECASE)),
    ("MS", re.compile(r"\b(?:M\.\s?S\.?|M\.?Sc\.?|MS|M\.?Eng\.?|(?i:master'?s)|Master of (?:Science|Engineering))(?=[\s,./)]|$)")),
    ("BS", re.compile(r"\b(?:B\.\s?S\.?|B\.?Sc\.?|BS|B\.?Eng\.?|bachelor'?s|Bachelor of (?:Science|Engineering|Arts)"
                      r"|B\.\s?A\.?|BA|undergraduate degree|four[- ]year degree)(?=[\s,./)]|$)", re.IGNORECASE)),
]
_RANK = {"BS": 1, "MS": 2, "PHD": 3}
# Separators are tried longest first: a greedy repeat stops at the first
# separator that is followed by a lowercase word, so "\s+" must come last.
FIELDS_RE = re.compile(r"\b(?:in|of)\s+((?:[A-Z][\w&/-]*(?:\s+(?:and|&|of|or|and/or)\s+|,\s*(?:or\s+|and\s+)?|\s+)?){1,40})")
RELATED_RE = re.compile(r"\b(?:or\s+(?:a\s+)?(?:closely\s+)?related|related\s+(?:field|discipline|area|major)"
                        r"|equivalent|similar\s+(?:field|discipline))", re.IGNORECASE)


_CONNECTOR_END = re.compile(r"(?:,|\b(?:and|or|a|an|the|of|in|to|for|with|by|from|as|on|at|least|than|between))$",
                            re.IGNORECASE)


def unwrap(text: str) -> str:
    """Join lines that were wrapped inside one bullet or sentence.

    Text copied out of a PDF or a narrow web page keeps its line breaks, so
    one requirement can arrive as two lines, and "or a related field" ends up
    cut off from the degree it qualifies. A line is joined to the one above
    when it is not a new bullet and either starts in lowercase or follows a
    line that ends mid-phrase (a comma or a word like "and", "of", "a")."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        prev = out[-1].rstrip() if out else ""
        if (s and prev and not re.match(r"[-•*·▪◦●■–]\s|\d+[.)]\s", s) and not prev.endswith((".", ":", ";", "!", "?"))
                and (s[0].islower() or _CONNECTOR_END.search(prev))):
            out[-1] = prev + " " + s
        else:
            out.append(line)
    return "\n".join(out)


def _sentences(text: str) -> list[str]:
    text = unwrap(text)
    # Split after a word of three or more lowercase letters or digits, so the
    # dots in "B.S.", "U.S." or "e.g." do not end a sentence.
    parts = re.split(r"(?<=[a-z0-9)]{3}[.;!?])\s+|\n+", text)
    return [p.strip(" -•*\t") for p in parts if p.strip(" -•*\t")]


def _ym(month: str | None, year: str, end: bool) -> str:
    if month:
        m = month.lower().rstrip(".")
        num = _SEASONS.get(m) or _MONTHS.get(m[:3])
    else:
        num = 12 if end else 1
    return f"{year}-{num:02d}"


def _fields(sentence: str) -> list[str]:
    """Fields of study named after "in"/"of" in a degree sentence."""
    out = []
    for m in FIELDS_RE.finditer(sentence):
        chunk = re.split(r"\b(?:graduat|with|from|and\s+(?:a|an|at)\b|by\b|or\s+(?:a\s+)?(?:closely\s+)?related)",
                         m.group(1))[0]
        for part in re.split(r",\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and/or\s+|/", chunk):
            part = re.sub(r"\s+(?:and|&|or)$", "", part.strip(" ,."))
            words = part.split()
            if not words or len(words) > 5 or not all(w[0].isupper() or w.lower() in {"and", "of", "&"} for w in words):
                continue
            if part.lower() in {"united states", "the united states", "us", "u.s."}:
                continue
            out.append(part)
    seen, unique = set(), []
    for f in out:
        if f.lower() not in seen:
            seen.add(f.lower())
            unique.append(f)
    return unique


def extract_knockouts(text: str) -> tuple[Knockouts, list[dict]]:
    """Rules found in a job description, and for each one the sentence it came from.

    Each evidence item: {"rule", "value", "enforced", "source"}; `enforced`
    is False for rules shown to the user but not applied (a field list that
    allows related fields)."""
    k = Knockouts()
    found: list[dict] = []

    def add(rule, value, source, enforced=True):
        found.append({"rule": rule, "value": value, "enforced": enforced, "source": source[:240]})

    for s in _sentences(text):
        degree_sentence = re.search(r"\b(?:degree|B\.\s?S|BS|B\.\s?A|bachelor|master|M\.\s?S|Ph\.?\s?D|pursuing|major)",
                                    s, re.IGNORECASE)
        if degree_sentence and k.min_degree_level is None:
            levels = [lvl for lvl, rx in LEVELS if rx.search(s)]
            if levels:
                k.min_degree_level = min(levels, key=_RANK.get)
                add("degree", {"BS": "Bachelor's", "MS": "Master's", "PHD": "Ph.D."}[k.min_degree_level]
                    + " or higher", s)
                fields = _fields(s)
                if fields:
                    related = bool(RELATED_RE.search(s))
                    if not related:
                        k.degree_fields = fields
                    add("field", ", ".join(fields) + (" or a related field" if related else ""), s, not related)
        if k.min_gpa is None and (m := GPA_RE.search(s)):
            g = float(m.group("g1") or m.group("g2"))
            if 1.5 <= g <= 4.0:
                k.min_gpa = g
                add("gpa", f"{g:.2f} or higher", s)
        if k.grad_window is None:
            if m := GRAD_BETWEEN.search(s):
                k.grad_window = (_ym(m.group("am"), m.group("ay"), False), _ym(m.group("bm"), m.group("by"), True))
            elif m := GRAD_BY.search(s):
                k.grad_window = ("1900-01", _ym(m.group("am"), m.group("ay"), True))
            elif m := GRAD_IN.search(s):
                y = m.group("cy") or m.group("ay")
                month = None if m.group("cy") else m.group("am")
                season = _SEASON_SPAN.get((month or "").lower())
                if season:  # "Spring 2027" is a range of months, not one
                    k.grad_window = (f"{y}-{season[0]:02d}", f"{y}-{season[1]:02d}")
                else:
                    k.grad_window = (_ym(month, y, False), _ym(month, y, True)) if month else (f"{y}-01", f"{y}-12")
            if k.grad_window:
                lo, hi = k.grad_window
                add("graduation", (f"by {hi}" if lo == "1900-01" else f"{lo} to {hi}"), s)
        if not k.require_work_authorization and AUTH_RE.search(s):
            k.require_work_authorization = True
            add("authorization", "Must be authorized to work", s)
        if not k.no_sponsorship and NO_SPONSOR_RE.search(s):
            k.no_sponsorship = True
            add("sponsorship", "No visa sponsorship", s)
    return k, found


def guess_title(text: str) -> str:
    """The posting's title: its first short line, if it looks like one."""
    for line in text.splitlines():
        s = line.strip(" -•*#\t")
        if not s:
            continue
        if len(s.split()) <= 12 and not s.endswith(".") and len(s) <= 90:
            return s
        break
    return "Pasted job description"
