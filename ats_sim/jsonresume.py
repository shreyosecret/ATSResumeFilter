"""The fictional personas as JSON Resume documents, and line labels for
resumes rendered from them by third-party JSON Resume themes.

JSON Resume (jsonresume.org) is an open resume format with hundreds of
community themes on npm, most under the MIT license. Rendering the same
personas through those themes tests the parsers on real designs that this
project did not write, while the answer key stays exact (the persona).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from .learn.labels import tokens

DEGREE_WORDS = {"BS": "Bachelor of Science", "BA": "Bachelor of Arts", "MS": "Master of Science",
                "PHD": "Doctor of Philosophy"}
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]
# Section titles themes commonly print; with the theme's own <h1>..<h6> texts
# they decide which lines are headings.
HEADING_WORDS = {
    "about", "about me", "summary", "profile", "objective", "work", "work experience", "experience",
    "professional experience", "employment", "employment history", "career", "education", "skills",
    "technical skills", "skills and tools", "projects", "personal projects", "side projects", "contact",
    "contact information", "contacts", "languages", "interests", "references", "awards", "publications",
    "volunteer", "volunteering", "certificates", "certifications", "basics", "info", "personal information",
}


def _iso(ym: str) -> str | None:
    return None if ym in (None, "", "present") else f"{ym}-01"


def to_jsonresume(p: dict) -> dict:
    city, _, region = p["location"].partition(", ")
    e = p["education"]
    edu = {"institution": e["school"], "area": e["field"],
           "studyType": DEGREE_WORDS.get(e["degree_level"], e["degree"]), "endDate": _iso(e["grad_date"])}
    if e.get("gpa"):
        edu["score"] = f"{e['gpa']:.2f}"
    work = []
    for x in p["experience"]:
        w = {"name": x["company"], "position": x["title"], "location": x.get("location", ""),
             "startDate": _iso(x["start"]), "highlights": x["bullets"]}
        if _iso(x["end"]):
            w["endDate"] = _iso(x["end"])
        work.append(w)
    return {
        "basics": {"name": p["name"], "email": p["email"], "phone": p["phone"],
                   "location": {"city": city, "region": region}, "profiles": []},
        "work": work,
        "education": [edu],
        "projects": [{"name": x["name"], "highlights": x["bullets"]} for x in p.get("projects", [])],
        "skills": [{"name": "Technical", "keywords": p["skills"]}],
    }


def _date_tokens(ym: str | None) -> list[str]:
    if not ym or ym == "present":
        return ["present", "current", "now", "today"]
    y, m = ym.split("-")[:2]
    month = _MONTHS[int(m) - 1]
    return [y, m, str(int(m)), "01", month, month[:3], month[:4]]


def references(p: dict) -> list[tuple[str, list[str]]]:
    """(label, tokens) for every piece of the persona a theme may print."""
    e = p["education"]
    refs = [("name", tokens(p["name"])),
            ("contact", tokens(p["email"]) + tokens(p["phone"]) + tokens(p["location"]))]
    for part in (p["email"], p["phone"], p["location"]):
        refs.append(("contact", tokens(part)))
    edu = tokens(" ".join([e["school"], e["field"], DEGREE_WORDS.get(e["degree_level"], ""), e["degree"],
                           e.get("location", ""), f"{e.get('gpa') or ''}", "gpa score"]))
    refs.append(("education", edu + _date_tokens(e["grad_date"])))
    for x in p["experience"]:
        head = tokens(" ".join([x["title"], x["company"], x.get("location", "")]))
        refs.append(("experience", head + _date_tokens(x["start"]) + _date_tokens(x["end"])))
        refs += [("experience", tokens(b)) for b in x["bullets"]]
    for x in p.get("projects", []):
        refs.append(("projects", tokens(x["name"])))
        refs += [("projects", tokens(b)) for b in x["bullets"]]
    refs.append(("skills", tokens(" ".join(p["skills"])) + ["technical"]))
    return refs


class _Headings(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.texts: list[str] = []
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r"h[1-6]", tag):
            self.depth += 1

    def handle_endtag(self, tag):
        if re.fullmatch(r"h[1-6]", tag) and self.depth:
            self.depth -= 1
            if not self.depth:
                self.texts.append(" ".join(self._buf))
                self._buf = []

    def handle_data(self, data):
        if self.depth:
            self._buf.append(data)


def theme_headings(html: str, p: dict) -> set[str]:
    """Section titles of one rendered theme: its <h1>..<h6> texts that are
    not persona content (job titles and names are often headings in HTML)."""
    h = _Headings()
    h.feed(html)
    content = {w for _, t in references(p) for w in t}
    out = set(HEADING_WORDS)
    for text in h.texts:
        t = tokens(text)
        if t and len(t) <= 4 and sum(w in content for w in t) / len(t) < 0.5:
            out.add(" ".join(t))
    return out


def label_lines(lines: list[str], p: dict, headings: set[str]) -> list[str]:
    """Each line's label: a heading if it is one of the theme's section
    titles, else the label of the persona part it overlaps most (as
    learn.labels.label_lines)."""
    refs = references(p)
    out = []
    for line in lines:
        t = tokens(line)
        if not t:
            out.append("other")
            continue
        if " ".join(t) in headings or ("".join(t) in {h.replace(" ", "") for h in headings} and len(t) > 2):
            out.append("heading")
            continue
        st = set(t)
        best, key = "other", (0.0, 0.0)
        for label, rt in refs:
            srt = set(rt)
            ov = len(st & srt)
            k = (ov / len(st), ov / len(st | srt) if st | srt else 0)
            if k > key:
                best, key = label, k
        out.append(best if key[0] >= 0.5 else "other")
    return out
