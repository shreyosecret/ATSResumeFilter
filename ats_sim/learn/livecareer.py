"""Section labels for the real resumes in the public LiveCareer dataset.

The Kaggle "Resume Dataset" (snehaanbhawal/resume-dataset, CC0 1.0) keeps each
resume's HTML beside its PDF. The HTML marks every section with a code
(id="SECTION_EXPR..." for experience, "SECTNAME_..." for the heading), so the
PDF's lines can be labeled without anyone reading them: find each line's text
in the HTML, in order, and take the section it falls in.

Names and contact details were removed by the dataset's author; the name slot
holds a job title instead, so those lines are not scored.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# Section code -> this project's label (learn.labels.LABELS); None = not scored
CODE_LABEL = {
    "NAME": None,
    "EXPR": "experience", "WRKH": "experience", "MILI": "experience", "EXFU": "experience", "EEXP": "experience",
    "EDUC": "education",
    "SKLL": "skills", "HILT": "skills", "TSKL": "skills", "LANG": "skills",
    "SUMM": "summary", "OBJC": "summary",
    "PRIN": "contact", "ALNK": "contact",
}
_SECTION = re.compile(r"SECTION_([A-Z]{4})")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


class _Walker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.code: str | None = None
        self.depth = 0
        self.title_depth: int | None = None
        self.chunks: list[tuple[str, str | None, bool]] = []  # (text, code, is_heading)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            self.depth += 1
            m = _SECTION.match(a.get("id") or "")
            if m:
                self.code = m.group(1)
            if "sectiontitle" in (a.get("class") or "").split() and self.title_depth is None:
                self.title_depth = self.depth

    def handle_endtag(self, tag):
        if tag == "div":
            if self.title_depth == self.depth:
                self.title_depth = None
            self.depth -= 1

    def handle_data(self, data):
        if data.strip():
            self.chunks.append((data, self.code, self.title_depth is not None))


def html_sections(html: str) -> list[tuple[str, str | None, bool]]:
    """The HTML's text in reading order: (text, section code, is a heading)."""
    w = _Walker()
    w.feed(html)
    return w.chunks


def _locate(stream: str, key: str, cursor: int, ahead: int = 400, around: int = 3000) -> range | None:
    """Where a line's letters are in the HTML: just ahead of the last match
    (the PDF and HTML read in the same order), else nearby in either direction
    (a two-column list reads across in the PDF but down in the HTML)."""
    for probe in (key, key[:16] if len(key) >= 24 else None):
        if not probe:
            continue
        at = stream.find(probe, cursor)
        if 0 <= at <= cursor + ahead:
            return range(at, at + len(probe))
        lo = max(0, cursor - around)
        at = stream.find(probe, lo, cursor + around)
        if at >= 0:
            return range(at, at + len(probe))
    return None


def gold_labels(lines: list[str], html: str) -> list[str | None]:
    """A label for each PDF line, or None where it cannot be told (the name
    slot, or text not found in the HTML)."""
    letters, owner = [], []
    for k, (text, _, _) in enumerate(chunks := html_sections(html)):
        n = _norm(text)
        letters.append(n)
        owner.extend([k] * len(n))
    stream = "".join(letters)
    out, cursor = [], 0
    for line in lines:
        key = _norm(line)
        if len(key) < 2:
            out.append(None)
            continue
        span = _locate(stream, key, cursor)
        if span is None:
            out.append(None)
            continue
        cursor = max(cursor, span.stop)
        votes: dict = {}
        for i in span:
            text, code, head = chunks[owner[i]]
            votes[(code, head)] = votes.get((code, head), 0) + 1
        code, head = max(votes, key=votes.get)
        if code is None or code == "NAME":
            out.append(None)
        elif head:
            out.append("heading")
        else:
            out.append(CODE_LABEL.get(code, "other"))
    return out


TRAIN_IDS = "livecareer_train_ids.json"  # in data/: the resumes the starting model learns from


def training_docs(data_dir) -> list[tuple]:
    """(lines, labels, geometry) for the real resumes listed in
    data/livecareer_train_ids.json, when the dataset has been downloaded
    (scripts/fetch_public_resumes.py --pdfs, or --train-pdfs for just these).
    Lines whose label cannot be told are left out. Empty if unavailable."""
    import json
    from pathlib import Path

    data_dir = Path(data_dir)
    ids_path, csv = data_dir / TRAIN_IDS, data_dir / "kaggle" / "Resume.csv"
    if not ids_path.exists() or not csv.exists():
        return []
    import pandas as pd

    from .geometry import read

    wanted = {int(x["id"]): x["category"] for x in json.loads(ids_path.read_text(encoding="utf-8"))["resumes"]}
    df = pd.read_csv(csv)
    out = []
    for r in df[df.ID.isin(wanted)].itertuples():
        pdf = data_dir / "kaggle" / "pdf" / r.Category / f"{r.ID}.pdf"
        if not pdf.exists():
            continue
        rows = read(pdf)
        lines = [x.text for x in rows]
        gold = gold_labels(lines, r.Resume_html)
        keep = [j for j, g in enumerate(gold) if g is not None]
        if keep:
            out.append(([lines[j] for j in keep], [gold[j] for j in keep], [rows[j].geo for j in keep]))
    return out
