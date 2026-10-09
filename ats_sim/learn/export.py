"""Export one resume's corrected line labels, to share for research on purpose.

The learned parser is tested on synthetic resumes and one real one; a set of
real, labeled resumes is the missing piece (README, Limitations). This turns a
resume's lines, the labels a person confirmed, and its page geometry into a
file they can choose to send. Nothing is sent by the app.

Contact details are masked first: the name line, email addresses, phone
numbers and links. The rest of the text stays, because the labels are about
that text, so the export says so and the person decides.
"""
from __future__ import annotations

import re

from .geometry import N_GEO
from .labels import LABELS

FORMAT = "ats-sim-corrections"
VERSION = 1
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
_LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|[\w-]+\.(?:com|org|io|dev|me|net))(?:/[\w./%-]*)?",
                   re.IGNORECASE)


def mask(line: str, label: str, name_words: set[str]) -> tuple[str, int]:
    """The line with contact details replaced, and how many were replaced."""
    if label == "name":
        return "Alex Morgan", 1
    n = 0
    for rx, repl in ((_EMAIL, "alex.morgan@example.com"), (_PHONE, "(555) 555-0100"), (_LINK, "example.com/profile")):
        line, k = rx.subn(repl, line)
        n += k
    if name_words:
        line, k = re.subn(r"\b(?:" + "|".join(map(re.escape, sorted(name_words))) + r")\b", "Morgan", line)
        n += k
    return line, n


def export(lines: list[str], labels: list[str], geo: list[list[float]] | None, app_version: str) -> dict:
    if len(lines) != len(labels) or (geo is not None and len(geo) != len(lines)):
        raise ValueError("lines, labels and geometry must line up")
    if set(labels) - set(LABELS):
        raise ValueError("unknown label")
    # The person's name, so it is also masked where it recurs (a header on page 2, a citation)
    name_words = {w for line, y in zip(lines, labels) if y == "name" for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", line)}
    out_lines, masked = [], 0
    for line, y in zip(lines, labels):
        text, n = mask(line, y, name_words)
        out_lines.append(text)
        masked += n
    return {"format": FORMAT, "version": VERSION, "app_version": app_version, "n_geo": N_GEO,
            "lines": out_lines, "labels": list(labels),
            "geo": [[round(float(v), 4) for v in g] for g in geo] if geo is not None else None,
            "masked": masked}


def load(path) -> tuple[list[str], list[str], list[list[float]] | None]:
    """Read an exported file back: (lines, labels, geo)."""
    import json
    from pathlib import Path

    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("format") != FORMAT:
        raise ValueError(f"{path} is not an {FORMAT} file")
    geo = d.get("geo")
    if geo is not None and d.get("n_geo") != N_GEO:
        geo = None  # made by a version with other geometry features; text only
    return d["lines"], d["labels"], geo
