"""Line-level training labels for rendered resumes.

Every rendered resume comes from a persona whose content is known, so each
line a parser extracts can be traced back to the section it came from. That
gives free, exact training labels for the line tagger without hand-labeling.
"""
from __future__ import annotations

import re

from ..render import RenderOptions, blocks, heading_for, line_text

LABELS = ("name", "contact", "heading", "summary", "education", "experience", "projects", "skills", "other")
SECTION_LABELS = ("summary", "education", "experience", "projects", "skills")


def tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9+#&]+", s.lower().replace("(cid:127)", " "))


def split_lines(text: str) -> list[str]:
    return [l for l in (x.strip() for x in text.splitlines()) if l]


def reference(persona: dict, template: str) -> tuple[list[tuple[str, list[str]]], set[str]]:
    """(label, tokens) for every source line, and the normalized heading strings."""
    opts = RenderOptions(template=template)
    b = blocks(persona, opts)
    refs: list[tuple[str, list[str]]] = [("name", tokens(persona["name"]))]
    for kind, text in b["contact"]:
        refs.append(("contact", tokens(line_text(kind, text))))
    headings = {" ".join(tokens(heading_for("contact", template)))}
    for key, lines in b.items():
        if key == "contact":
            continue
        label = key if key in SECTION_LABELS else "other"
        headings.add(" ".join(tokens(heading_for(key, template))))
        for kind, text in lines:
            refs.append((label, tokens(line_text(kind, text))))
    return refs, headings


def _is_heading_fragment(t: list[str], headings: set[str]) -> bool:
    """A heading wrapped onto two lines (narrow table cells) arrives in pieces."""
    line = " ".join(t)
    return any(f" {line} " in f" {h} " for h in headings if len(h.split()) > len(t))


def label_lines(lines: list[str], persona: dict, template: str) -> list[str]:
    """Assign each extracted line the label of the source line it overlaps most.

    Wrapped lines are fragments of one source line, so token containment
    (share of the extracted line's tokens found in a source line) identifies
    them; ties go to the source line closest in size (Jaccard). Lines that
    merge several source lines of one section (a contact row in a table)
    fall back to containment in all of that section's tokens together.
    """
    refs, headings = reference(persona, template)
    by_label: dict[str, set[str]] = {}
    for label, rt in refs:
        by_label.setdefault(label, set()).update(rt)
    out = []
    for line in lines:
        t = tokens(line)
        if not t:
            out.append("other")
            continue
        if " ".join(t) in headings or _is_heading_fragment(t, headings):
            out.append("heading")
            continue
        best, best_key = "other", (0.0, 0.0)
        st = set(t)
        for label, rt in refs:
            if not rt:
                continue
            srt = set(rt)
            overlap = len(st & srt)
            key = (overlap / len(st), overlap / len(st | srt))
            if key > best_key:
                best, best_key = label, key
        if best_key[0] < 0.5:
            union = max(by_label.items(), key=lambda kv: len(st & kv[1]))
            best, best_key = (union[0], (len(st & union[1]) / len(st), 0.0)) if len(st & union[1]) / len(st) >= 0.8 else ("other", best_key)
        out.append(best if best_key[0] >= 0.5 else "other")
    return out
