"""How each line looks on the page, measured from individual characters.

The text alone hides most of what a person uses to read a resume: a heading
is bigger, bolder, set apart by white space, sometimes letter-spaced or
underlined; a sidebar sits at a different margin; dates hug the right edge.
This module measures those cues for every line the layout-aware reader
produces, from the smallest unit the PDF offers (single characters: their
position, size, font and color) and, for Word files, from paragraph and run
formatting.

`read(path)` returns the same lines as
`split_lines(extract_text(path, layout_aware=True))`, each with a fixed-length
feature vector (GEO_FEATURES). A line whose characters cannot be found on the
page keeps the text and gets zeros with has_geometry = 0.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path

GEO_FEATURES = (
    "has_geometry", "size_ratio", "is_largest", "bold", "italic", "colored", "x0", "x1", "width",
    "right_aligned", "centered", "gap_above", "gap_below", "y", "letter_spacing", "single_letter_words",
    "rule_below", "shaded", "in_table", "in_box", "page", "indent_change",
)
N_GEO = len(GEO_FEATURES)
_BOLD = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
_ITALIC = re.compile(r"italic|oblique", re.IGNORECASE)


@dataclass
class Line:
    text: str
    geo: list[float]


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _is_colored(color) -> bool:
    if color is None:
        return False
    if isinstance(color, (int, float)):
        return False  # gray scale
    c = tuple(color)
    if len(c) == 3:
        return max(c) - min(c) > 0.15
    if len(c) == 4:
        return max(c[:3]) > 0.15
    return False


# -------------------------------------------------------------------- PDF

def _match_lines(page_lines: list[str], words: list[dict]) -> list[list[dict]]:
    """Find, for each extracted line, the page words it was made of.

    Lines come from the layout-aware reader, which builds them out of the same
    words, so each line's first word is matched to an unused occurrence whose
    row also holds the line's following words; ties go to reading order."""
    by_text: dict[str, list[int]] = {}
    for i, w in enumerate(words):
        by_text.setdefault(w["text"], []).append(i)
    used = [False] * len(words)
    out = []
    for line in page_lines:
        toks = line.split()
        best, best_score = None, -1
        for i in by_text.get(toks[0], []) if toks else []:
            if used[i]:
                continue
            row = [j for j, w in enumerate(words) if not used[j] and abs(w["top"] - words[i]["top"]) < 2.5
                   and w["x0"] >= words[i]["x0"] - 0.5]
            row.sort(key=lambda j: words[j]["x0"])
            chosen, k = [], 0
            for j in row:
                if k < len(toks) and words[j]["text"] == toks[k]:
                    chosen.append(j)
                    k += 1
            if len(chosen) > best_score:
                best, best_score = chosen, len(chosen)
                if best_score == len(toks):
                    break
        for j in best or []:
            used[j] = True
        out.append([words[j] for j in best or []])
    return out


def _regions(page) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Table cells, filled boxes, and thin horizontal rules on the page."""
    tables = [t.bbox for t in page.find_tables()]
    boxes, rules = [], []
    for r in page.rects:
        w, h = r["x1"] - r["x0"], r["bottom"] - r["top"]
        if h <= 2.5 and w > 30:
            rules.append((r["x0"], r["top"], r["x1"], r["bottom"]))
        elif w >= 40 and h >= 20 and r.get("fill"):
            fill = r.get("non_stroking_color")
            white = fill is None or (isinstance(fill, (tuple, list)) and len(fill) in (1, 3) and min(fill) > 0.97)
            if not white:
                boxes.append((r["x0"], r["top"], r["x1"], r["bottom"]))
    for ln in page.lines:
        if abs(ln["top"] - ln["bottom"]) <= 1.5 and ln["x1"] - ln["x0"] > 30:
            rules.append((ln["x0"], ln["top"], ln["x1"], ln["bottom"]))
    return tables, boxes, rules


def _inside(x0, top, x1, bottom, bbox) -> bool:
    cx, cy = (x0 + x1) / 2, (top + bottom) / 2
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def read_pdf(path: str | Path) -> list[Line]:
    import pdfplumber

    from ..parser import _layout_aware_page_text
    from .labels import split_lines

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages):
            lines = split_lines(_layout_aware_page_text(page))
            words = page.extract_words(return_chars=True)
            pages.append((pno, page.width, page.height, lines, _match_lines(lines, words), _regions(page)))

    sizes = [c["size"] for *_, matched, _ in pages for ws in matched for w in ws for c in w["chars"]]
    body = statistics.median(sizes) if sizes else 10.0
    largest = max(sizes) if sizes else 10.0
    out: list[Line] = []
    for pno, W, H, lines, matched, (tables, boxes, rules) in pages:
        geo_rows = []
        for ws in matched:
            chars = [c for w in ws for c in w["chars"]]
            if not chars:
                geo_rows.append(None)
                continue
            x0, x1 = min(w["x0"] for w in ws), max(w["x1"] for w in ws)
            top, bottom = min(w["top"] for w in ws), max(w["bottom"] for w in ws)
            size = statistics.mean(c["size"] for c in chars)
            gaps = [b["x0"] - a["x1"] for w in ws for a, b in zip(w["chars"], w["chars"][1:])]
            geo_rows.append(dict(
                x0=x0, x1=x1, top=top, bottom=bottom, size=size,
                bold=sum(bool(_BOLD.search(c["fontname"])) for c in chars) / len(chars),
                italic=sum(bool(_ITALIC.search(c["fontname"])) for c in chars) / len(chars),
                colored=sum(_is_colored(c.get("non_stroking_color")) for c in chars) / len(chars),
                spacing=(statistics.mean(gaps) / size) if gaps else 0.0,
                single=sum(len(w["text"]) == 1 for w in ws) / len(ws),
            ))
        found = [g for g in geo_rows if g]
        left = min((g["x0"] for g in found), default=0.0)
        right = max((g["x1"] for g in found), default=W)
        for i, (text, g) in enumerate(zip(lines, geo_rows)):
            if g is None:
                out.append(Line(text, [0.0] * N_GEO))
                continue
            prev = next((geo_rows[j] for j in range(i - 1, -1, -1) if geo_rows[j]), None)
            nxt = next((geo_rows[j] for j in range(i + 1, len(geo_rows)) if geo_rows[j]), None)
            above = (g["top"] - prev["bottom"]) / body if prev and prev["bottom"] <= g["top"] + 1 else 1.0
            below = (nxt["top"] - g["bottom"]) / body if nxt and nxt["top"] >= g["bottom"] - 1 else 1.0
            width = g["x1"] - g["x0"]
            mid = (g["x0"] + g["x1"]) / 2
            out.append(Line(text, [
                1.0, _clip(g["size"] / body, 0, 3) / 3, float(g["size"] >= 0.98 * largest),
                g["bold"], g["italic"], g["colored"], g["x0"] / W, g["x1"] / W, width / W,
                float(right - g["x1"] < 3 and g["x0"] - left > 0.3 * W),
                float(abs(mid - (left + right) / 2) < 6 and g["x0"] - left > 20),
                _clip(above, 0, 4) / 4, _clip(below, 0, 4) / 4, g["top"] / H,
                _clip(g["spacing"], 0, 1), g["single"],
                float(any(r[1] >= g["bottom"] - 1 and r[1] - g["bottom"] < 6 and r[0] <= g["x1"] and r[2] >= g["x0"]
                          for r in rules)),
                float(any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], b) for b in boxes)),
                float(any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], t) for t in tables)),
                float(any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], b) for b in boxes)
                      or any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], t) for t in tables)),
                _clip(pno, 0, 3) / 3,
                _clip(((g["x0"] - prev["x0"]) / W) if prev else 0.0, -0.5, 0.5),
            ]))
    return out


# -------------------------------------------------------------------- DOCX

def _run_size(run, para, default: float) -> float:
    for s in (run.font.size, para.style.font.size if para.style is not None else None):
        if s is not None:
            return s.pt
    return default


def _para_features(para, doc_default: float, in_table: bool, in_box: bool) -> dict:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn

    runs = [r for r in para.runs if r.text.strip()]
    n = sum(len(r.text) for r in runs) or 1
    style_bold = bool(para.style is not None and para.style.font.bold)
    bold = sum(len(r.text) for r in runs if r.bold or (r.bold is None and style_bold)) / n
    italic = sum(len(r.text) for r in runs if r.italic) / n
    colored = sum(len(r.text) for r in runs if r.font.color is not None and r.font.color.rgb is not None
                  and str(r.font.color.rgb) not in ("000000", "FFFFFF")) / n
    size = (sum(_run_size(r, para, doc_default) * len(r.text) for r in runs) / n) if runs else doc_default
    spacing = 0.0
    for r in runs:
        sp = r._r.find(f"{qn('w:rPr')}/{qn('w:spacing')}")
        if sp is not None:
            spacing = max(spacing, int(sp.get(qn("w:val"), "0")) / 20 / max(size, 1))
    pf = para.paragraph_format
    indent = pf.left_indent.pt if pf.left_indent is not None else 0.0
    before = pf.space_before.pt if pf.space_before is not None else 0.0
    style_name = (para.style.name or "").lower() if para.style is not None else ""
    return dict(size=size, bold=bold, italic=italic, colored=colored, spacing=spacing, indent=indent,
                before=before, align=pf.alignment, heading_style="heading" in style_name or "title" in style_name,
                right=pf.alignment == WD_ALIGN_PARAGRAPH.RIGHT, centered=pf.alignment == WD_ALIGN_PARAGRAPH.CENTER,
                in_table=in_table, in_box=in_box,
                rule=para._p.find(f"{qn('w:pPr')}/{qn('w:pBdr')}") is not None)


def read_docx(path: str | Path) -> list[Line]:
    """Paragraph formatting for each line, in the order extract_text_docx
    (layout-aware) reads them."""
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    default = d.styles["Normal"].font.size.pt if d.styles["Normal"].font.size else 11.0
    paras: list[tuple] = []

    def boxes_of(p_element, parent):
        for box in p_element.iter(qn("w:txbxContent")):
            anc, fallback = box.getparent(), False
            while anc is not None and anc is not p_element:
                if anc.tag.endswith("}Fallback"):
                    fallback = True
                    break
                anc = anc.getparent()
            if not fallback:
                for p in box.iter(qn("w:p")):
                    paras.append((Paragraph(p, parent), False, True))

    def walk_table(table):
        for row in table.rows:
            seen = set()
            for cell in row.cells:
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                for block in cell._tc.iterchildren():
                    tag = block.tag.rsplit("}", 1)[-1]
                    if tag == "p":
                        paras.append((Paragraph(block, cell), True, False))
                    elif tag == "tbl":
                        walk_table(Table(block, cell))

    for block in d.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paras.append((Paragraph(block, d), False, False))
            boxes_of(block, d)
        elif tag == "tbl":
            walk_table(Table(block, d))

    feats, texts = [], []
    for para, in_table, in_box in paras:
        for sub in para.text.splitlines():
            if sub.strip():
                texts.append(sub.strip())
                feats.append(_para_features(para, default, in_table, in_box))
    sizes = [f["size"] for f in feats]
    body = statistics.median(sizes) if sizes else default
    largest = max(sizes) if sizes else default
    out = []
    for i, (t, f) in enumerate(zip(texts, feats)):
        prev_indent = feats[i - 1]["indent"] if i else f["indent"]
        out.append(Line(t, [
            1.0, _clip(f["size"] / body, 0, 3) / 3, float(f["size"] >= 0.98 * largest), f["bold"], f["italic"],
            f["colored"], _clip(f["indent"] / 612, 0, 1), 0.0, 0.0, float(f["right"] or "\t" in t),
            float(f["centered"]), _clip(f["before"] / max(body, 1), 0, 4) / 4, 0.0, i / max(len(texts) - 1, 1),
            _clip(f["spacing"], 0, 1), sum(len(w) == 1 for w in t.split()) / max(len(t.split()), 1),
            float(f["rule"] or f["heading_style"]), 0.0, float(f["in_table"]), float(f["in_box"] or f["in_table"]),
            0.0, _clip((f["indent"] - prev_indent) / 612, -0.5, 0.5),
        ]))
    return out


def read(path: str | Path) -> list[Line]:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix == ".docx":
        return read_docx(path)
    from .labels import split_lines

    return [Line(t, [0.0] * N_GEO) for t in split_lines(Path(path).read_text())]
