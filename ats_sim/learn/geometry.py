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
    "right_aligned", "centered", "gap_above", "gap_below", "letter_spacing", "single_letter_words",
    "rule_below", "shaded", "in_table", "in_box", "indent_change",
)
# No absolute page number or height on the page: every training resume is one
# page, so those features never varied in training, kept their random initial
# weights, and threw off every line on page 2 of a real two-page resume.
N_GEO = len(GEO_FEATURES)
_BOLD = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:\(cid:127\)|[•\-\*·▪◦●■–>])")
_ITALIC = re.compile(r"italic|oblique", re.IGNORECASE)
# Contact details stacked one per line are separate items, not a wrap.
_CONTACT = re.compile(r"@|https?://|www\.|linkedin|github\.com|^\+?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}",
                      re.IGNORECASE)
# Starts of a new item even without a bullet glyph: a "Label:" (skills,
# contact), a past-tense action verb, or a degree.
_NEW_ITEM = re.compile(r"^(?:[A-Z][\w&/+ ]{0,24}:\s|[A-Z][a-z]+ed\b|(?:Wrote|Built|Led|Ran|Made|Won|Taught|Grew|Cut"
                       r"|Drew|Oversaw|Sold|Spoke|Took|Gave|Held|Kept|Began|Brought|Bachelor|Master|B\.\s?[SA]\.|M\.\s?S\.)\b)")


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
    words, so each line's first word is matched to an unused occurrence that
    the line's following words directly follow on its row; ties go to reading
    order."""
    by_text: dict[str, list[int]] = {}
    for i, w in enumerate(words):
        by_text.setdefault(w["text"], []).append(i)
    used = [False] * len(words)
    out: list[list[dict] | None] = [None] * len(page_lines)

    def best_for(line: str):
        toks = line.split()
        best, best_score = None, -1
        for i in by_text.get(toks[0], []) if toks else []:
            if used[i]:
                continue
            row = [j for j, w in enumerate(words) if not used[j] and abs(w["top"] - words[i]["top"]) < 2.5
                   and w["x0"] >= words[i]["x0"] - 0.5]
            row.sort(key=lambda j: words[j]["x0"])
            row = row[row.index(i):]
            chosen = []  # consecutive words only: "(cid:127) TypeScript" must not match
            for j, tok in zip(row, toks):  # a bullet and a word further along another line
                if words[j]["text"] != tok:
                    break
                chosen.append(j)
            if len(chosen) > best_score:
                best, best_score = chosen, len(chosen)
                if best_score == len(toks):
                    break
        return best or [], best_score == len(toks)

    # Lines whose words all match are placed first, so a line that only half
    # matches cannot take a shared first word (a bullet glyph) from another.
    for full_pass in (True, False):
        for n, line in enumerate(page_lines):
            if out[n] is not None:
                continue
            best, full = best_for(line)
            if full_pass and not full:
                continue
            for j in best:
                used[j] = True
            out[n] = [words[j] for j in best]
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


def _continues(block: dict, g: dict, text: str, block_text: str, col_right: float) -> bool:
    """Is this line the wrapped continuation of the block above it?

    A wrapped line sits directly below at normal line spacing, in the same
    size and weight, starts where the block's text starts (after a bullet's
    hanging indent), is not a new bullet, and its first word would not have
    fit at the end of the line before it. A line ending in a right-aligned date or a colon
    is complete, and stacked contact details (email, phone, links) are
    separate items, so nothing joins those. Nor does a line that reads like
    the start of a new item (_NEW_ITEM), for bullets drawn without a glyph."""
    if _BULLET.match(text) or block_text.rstrip().endswith(":") or block["last_gap"]:
        return False
    if _NEW_ITEM.match(text) or _CONTACT.search(text) or _CONTACT.search((block_text.split() or [""])[-1]):
        return False
    gap = g["top"] - block["bottom"]
    if not (-1 <= gap <= 0.6 * block["last_size"]) or abs(g["size"] - block["last_size"]) > 0.6:
        return False
    if abs(g["bold"] - block["last_bold"]) > 0.5:
        return False
    if not (block["text_x0"] - 3 <= g["x0"] <= block["text_x0"] + 12):
        return False
    # Word wrap moves a word down only when it does not fit: had this line's
    # first word fit after the line above (with a space), it is a new item.
    return block["last_x1"] + 0.25 * g["size"] + g["first_w"] > col_right - 2


def _merge_wrapped(lines: list[str], rows: list[dict | None], width: float) -> tuple[list[str], list[dict | None]]:
    """Join lines that a PDF wrapped back into the bullet or paragraph they
    came from (a PDF stores each visual line separately)."""
    found = [g for g in rows if g]
    out_t: list[str] = []
    out_g: list[dict | None] = []
    for text, g in zip(lines, rows):
        block = out_g[-1] if out_g else None
        if g is not None and block is not None:
            same_col = [r for r in found if abs(r["x0"] - block["x0"]) < 0.06 * width
                        or abs(r["x0"] - block["text_x0"]) < 0.06 * width]
            col_right = max((r["x1"] for r in same_col), default=block["last_x1"])
            if _continues(block, g, text, out_t[-1], col_right):
                prev = out_t[-1]
                out_t[-1] = prev[:-1] + text if prev.endswith("-") and text[:1].islower() else prev + " " + text
                n0, n1 = len(prev), len(text)
                for k in ("bold", "italic", "colored"):
                    block[k] = (block[k] * n0 + g[k] * n1) / (n0 + n1)
                block.update(x1=max(block["x1"], g["x1"]), bottom=g["bottom"], last_x1=g["x1"],
                             last_size=g["size"], last_bold=g["bold"], last_gap=g["gap"], parts=block["parts"] + 1)
                continue
        out_t.append(text)
        out_g.append(None if g is None else {**g, "last_x1": g["x1"], "last_size": g["size"], "last_bold": g["bold"],
                                             "last_gap": g["gap"], "parts": 1})
    return out_t, out_g


def read_pdf(path: str | Path, merge_wrapped: bool = True) -> list[Line]:
    """`merge_wrapped` joins lines the PDF wrapped back into whole bullets and
    paragraphs; with False the lines are exactly the text reader's."""
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
            word_gaps = [b["x0"] - a["x1"] for a, b in zip(ws, ws[1:])]
            bullet = bool(_BULLET.match(ws[0]["text"])) or ws[0]["text"] == "(cid:127)"
            geo_rows.append(dict(
                x0=x0, x1=x1, top=top, bottom=bottom, size=size,
                text_x0=ws[1]["x0"] if bullet and len(ws) > 1 else x0,
                # a wide space means a separately placed part (a right-aligned date or place)
                gap=bool(word_gaps) and max(word_gaps) > 1.2 * size,
                first_w=ws[0]["x1"] - ws[0]["x0"],
                bold=sum(bool(_BOLD.search(c["fontname"])) for c in chars) / len(chars),
                italic=sum(bool(_ITALIC.search(c["fontname"])) for c in chars) / len(chars),
                colored=sum(_is_colored(c.get("non_stroking_color")) for c in chars) / len(chars),
                spacing=(statistics.mean(gaps) / size) if gaps else 0.0,
                single=sum(len(w["text"]) == 1 for w in ws) / len(ws),
            ))
        if merge_wrapped:
            lines, geo_rows = _merge_wrapped(lines, geo_rows, W)
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
                _clip(above, 0, 4) / 4, _clip(below, 0, 4) / 4,
                _clip(g["spacing"], 0, 1), g["single"],
                float(any(r[1] >= g["bottom"] - 1 and r[1] - g["bottom"] < 6 and r[0] <= g["x1"] and r[2] >= g["x0"]
                          for r in rules)),
                float(any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], b) for b in boxes)),
                float(any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], t) for t in tables)),
                float(any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], b) for b in boxes)
                      or any(_inside(g["x0"], g["top"], g["x1"], g["bottom"], t) for t in tables)),
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
            float(f["centered"]), _clip(f["before"] / max(body, 1), 0, 4) / 4, 0.0,
            _clip(f["spacing"], 0, 1), sum(len(w) == 1 for w in t.split()) / max(len(t.split()), 1),
            float(f["rule"] or f["heading_style"]), 0.0, float(f["in_table"]), float(f["in_box"] or f["in_table"]),
            _clip((f["indent"] - prev_indent) / 612, -0.5, 0.5),
        ]))
    return out


def read(path: str | Path, merge_wrapped: bool = True) -> list[Line]:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path, merge_wrapped)
    if suffix == ".docx":
        return read_docx(path)
    from .labels import split_lines

    return [Line(t, [0.0] * N_GEO) for t in split_lines(Path(path).read_text(encoding="utf-8"))]
