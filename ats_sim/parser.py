"""A deliberately naive resume parser.

It behaves the way many real ATS parsers are documented to behave: extract
text in reading order with no layout understanding, find section headings by
matching known heading words, then pull fields out with regexes. That naivety
is the point. It lets the layout experiment measure how much information a
simple text-order parser loses on multi-column, table and text-box designs.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import ExperienceEntry, ParsedResume

SECTION_HEADINGS: dict[str, set[str]] = {
    "summary": {"summary", "profile", "objective", "professional summary", "about me"},
    "contact": {"contact", "contact information", "contact info"},
    "education": {"education", "academic background", "academics", "education and training"},
    "experience": {
        "experience", "work experience", "professional experience", "employment",
        "employment history", "relevant experience", "work history",
    },
    "skills": {
        "skills", "technical skills", "core competencies", "skills and tools",
        "skills & tools", "technologies", "tools", "skills & interests",
    },
    "projects": {"projects", "academic projects", "selected projects", "project experience"},
    "certifications": {"certifications", "licenses", "certificates"},
    "leadership": {"leadership", "activities", "leadership and activities", "involvement"},
    "awards": {"awards", "honors", "honors and awards"},
}
_HEADING_LOOKUP = {h: sec for sec, hs in SECTION_HEADINGS.items() for h in hs}

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
MONTH_YEAR_RE = re.compile(rf"\b({_MONTH_RE})\s+((?:19|20)\d\d)\b", re.IGNORECASE)
NUMERIC_DATE_RE = re.compile(r"\b(0?[1-9]|1[0-2])/((?:19|20)\d\d)\b")
_DATE_TOKEN = rf"(?:{_MONTH_RE}\s+(?:19|20)\d\d|(?:0?[1-9]|1[0-2])/(?:19|20)\d\d)"
DATE_RANGE_RE = re.compile(
    rf"({_DATE_TOKEN})\s*(?:[-–—]|to)\s*({_DATE_TOKEN}|Present|Current)", re.IGNORECASE
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
GPA_RE = re.compile(r"\bGPA\b\s*[:\-]?\s*([0-4]\.\d{1,2})", re.IGNORECASE)

DEGREE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PHD", re.compile(r"\b(?:Ph\.?\s?D\.?|Doctor of Philosophy)", re.IGNORECASE)),
    ("MS", re.compile(r"\b(?:M\.\s?S\.|M\.?Sc\.?|MS|Master of Science|M\.?Eng\.?|Master of Engineering)(?=\s|,|$)")),
    ("BS", re.compile(r"\b(?:B\.\s?S\.|B\.?Sc\.?|BS|Bachelor of Science|B\.?Eng\.?|Bachelor of Engineering)(?=\s|,|$)")),
    ("BA", re.compile(r"\b(?:B\.\s?A\.|BA|Bachelor of Arts)(?=\s|,|$)")),
]
DEGREE_RANK = {"BA": 1, "BS": 1, "MS": 2, "PHD": 3}
FIELD_RE = re.compile(r"\bin[ \t]+((?:[A-Z][A-Za-z&]*)(?:[ \t]+(?:and|of|&|[A-Z][A-Za-z&]*))*)")
SCHOOL_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z.&'-]+[ \t]+)*(?:University|College|Institute|Polytechnic)"
    r"(?:[ \t]+(?:of|at|for)(?:[ \t]+[A-Z][A-Za-z.&'-]+)+)?)"
)
_SCHOOL_TRAILING = re.compile(r"\s+(?:Expected|GPA|Graduated|Class)\b.*$")


def month_year_to_iso(month: str, year: str) -> str:
    return f"{int(year):04d}-{MONTHS[month.lower()[:3]]:02d}"


# ---------------------------------------------------------------- extraction

def _is_visible_char(obj: dict) -> bool:
    if obj.get("object_type") != "char":
        return True
    if obj.get("size", 10) < 4:
        return False
    color = obj.get("non_stroking_color")
    if color is None:
        return True
    if isinstance(color, (int, float)):
        color = (color,)
    color = tuple(color)
    if len(color) == 1:
        return color[0] < 0.95
    if len(color) == 3:
        return min(color) < 0.95
    if len(color) == 4:  # CMYK: white is all zeros
        return max(color) > 0.05
    return True


def extract_text_pdf(path: str | Path, drop_invisible: bool = False, layout_aware: bool = False) -> str:
    """Page-by-page text in the order pdfplumber reads it (top-to-bottom, left-to-right).

    `drop_invisible` is a defense used only in the keyword-stuffing audit: it
    discards tiny or white characters before extraction. The default parser
    does not do this, matching common parser behavior.

    `layout_aware` switches to the reading order in `_layout_aware_page_text`.
    """
    import pdfplumber

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            if drop_invisible:
                page = page.filter(_is_visible_char)
            pages.append(_layout_aware_page_text(page) if layout_aware else (page.extract_text() or ""))
    return "\n".join(pages)


# ------------------------------------------------- layout-aware reading order

def _inside(obj: dict, bbox: tuple) -> bool:
    x0, top, x1, bottom = bbox
    cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
    return x0 <= cx <= x1 and top <= cy <= bottom


def find_gutter(words: list[dict], page_width: float, pad: float = 4.0, min_side: float = 0.15) -> float | None:
    """x position of a vertical gutter that splits the words into two columns.

    A gutter is a vertical line that no word crosses (allowing 1% noise) and
    that has at least `min_side` of the words on each side. Single-column text
    always has lines that run across the middle, so it has no gutter.
    """
    if len(words) < 20:
        return None
    best, best_cross = None, None
    for i in range(int(page_width * 0.15), int(page_width * 0.85), 2):
        x = float(i)
        cross = sum(1 for w in words if w["x0"] - pad < x < w["x1"] + pad)
        left = sum(1 for w in words if w["x1"] <= x)
        if min(left, len(words) - left - cross) < min_side * len(words):
            continue
        if best_cross is None or cross < best_cross:
            best, best_cross = x, cross
    if best is None or best_cross > 0.01 * len(words):
        return None
    return best


def _region_text(page, bbox) -> str:
    return page.within_bbox(bbox).extract_text() or ""


def _table_text(table) -> str:
    lines = []
    for row in table.extract():
        for cell in row:
            if cell:
                lines.append(cell)
    return "\n".join(lines)


def _box_regions(page, taken: list[tuple]) -> list[tuple]:
    """Bordered or shaded rectangles big enough to hold text (text boxes)."""
    boxes = []
    for r in page.rects:
        w, h = r["x1"] - r["x0"], r["bottom"] - r["top"]
        if w < 40 or h < 20 or w > page.width * 0.9:
            continue
        bbox = (r["x0"], r["top"], r["x1"], r["bottom"])
        if any(_inside({"x0": bbox[0], "x1": bbox[2], "top": bbox[1], "bottom": bbox[3]}, t) for t in taken):
            continue
        boxes.append(bbox)
    return boxes


def _layout_aware_page_text(page) -> str:
    """Reading order that understands tables, boxes and columns.

    1. Ruled tables (found from the page's lines) are read cell by cell, row
       by row; bordered or shaded boxes are read as one block each.
    2. Remaining text is checked for a column gutter; if there is one, the
       left column is read before the right column.
    3. Blocks that sit beside the main text (a floating box in the margin)
       are read after the main text; blocks inside its span are read in
       vertical order.

    This is roughly what layout-analysis parsers do. It is still heuristic:
    one gutter per page, no nested columns, no reading of images.
    """
    W, H = page.width, page.height
    blocks = [(t.bbox, _table_text(t)) for t in page.find_tables()]
    blocks += [(b, _region_text(page, b)) for b in _box_regions(page, [b for b, _ in blocks])]
    regions = [b for b, _ in blocks]
    free = page.filter(lambda o: not any(_inside(o, r) for r in regions)) if regions else page
    words = free.extract_words()
    if words:
        main_x0, main_x1 = min(w["x0"] for w in words), max(w["x1"] for w in words)
    else:
        main_x0, main_x1 = 0, W

    inline, sidebar = [], []
    for bbox, text in sorted(blocks, key=lambda b: b[0][1]):
        beside = bbox[0] >= main_x1 - 2 or bbox[2] <= main_x0 + 2
        (sidebar if beside and words else inline).append((bbox, text))

    gutter = find_gutter(words, W)

    def free_band(top: float, bottom: float) -> str:
        if bottom - top < 1:
            return ""
        if gutter is None:
            return _region_text(free, (0, top, W, bottom))
        return "\n".join(filter(None, (_region_text(free, (0, top, gutter, bottom)),
                                       _region_text(free, (gutter, top, W, bottom)))))

    parts, cursor = [], 0.0
    for bbox, text in inline:
        parts.append(free_band(cursor, bbox[1]))
        parts.append(text)
        cursor = max(cursor, bbox[3])
    parts.append(free_band(cursor, H))
    parts += [text for _, text in sidebar]
    return "\n".join(p for p in parts if p.strip())


def _textbox_lines(p_element, parent) -> list[str]:
    """Paragraphs inside text boxes anchored to this paragraph (skipping the
    duplicate copy Word stores under mc:Fallback)."""
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    out = []
    for box in p_element.iter(qn("w:txbxContent")):
        anc, fallback = box.getparent(), False
        while anc is not None and anc is not p_element:
            if anc.tag.endswith("}Fallback"):
                fallback = True
                break
            anc = anc.getparent()
        if not fallback:
            out += [Paragraph(p, parent).text for p in box.iter(qn("w:p"))]
    return out


def extract_text_docx(path: str | Path, layout_aware: bool = False) -> str:
    """Body paragraphs and table cells in document order.

    Like many simple DOCX readers built on python-docx, this does not descend
    into text boxes, headers or footers. With `layout_aware`, text-box content
    is read right after the paragraph it is anchored to.
    """
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))
    lines: list[str] = []

    def walk_table(table: Table) -> None:
        for row in table.rows:
            seen = set()
            for cell in row.cells:
                if id(cell._tc) in seen:  # merged cells repeat in python-docx
                    continue
                seen.add(id(cell._tc))
                for block in cell._tc.iterchildren():
                    tag = block.tag.rsplit("}", 1)[-1]
                    if tag == "p":
                        lines.append(Paragraph(block, cell).text)
                    elif tag == "tbl":
                        walk_table(Table(block, cell))

    for block in doc.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(Paragraph(block, doc).text)
            if layout_aware:
                lines += _textbox_lines(block, doc)
        elif tag == "tbl":
            walk_table(Table(block, doc))
    return "\n".join(lines)


def extract_text(path: str | Path, drop_invisible: bool = False, layout_aware: bool = False) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return extract_text_pdf(path, drop_invisible=drop_invisible, layout_aware=layout_aware)
    if suffix == ".docx":
        return extract_text_docx(path, layout_aware=layout_aware)
    if suffix in {".txt", ".md"}:
        return Path(path).read_text()
    raise ValueError(f"Unsupported resume format: {suffix}")


# ---------------------------------------------------------------- sections

def normalize_heading(line: str) -> str:
    s = line.strip().lower().rstrip(":").strip()
    return re.sub(r"\s+", " ", s)


def split_sections(text: str) -> dict[str, str]:
    """Split text into sections at lines that exactly match a known heading."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.splitlines():
        key = _HEADING_LOOKUP.get(normalize_heading(line))
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


# ---------------------------------------------------------------- fields

def extract_name(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _HEADING_LOOKUP.get(normalize_heading(s)) or EMAIL_RE.search(s) or PHONE_RE.search(s):
            return None
        tokens = s.split()
        if 2 <= len(tokens) <= 4 and all(re.fullmatch(r"[A-Z][a-zA-Z'.-]*", t) for t in tokens):
            return s
        return None  # naive: the name must be the first non-empty line
    return None


def extract_degree(text: str) -> tuple[str | None, str | None]:
    for level, pat in DEGREE_PATTERNS:
        m = pat.search(text)
        if m:
            field_m = FIELD_RE.match(text, m.end()) or FIELD_RE.search(text[m.end(): m.end() + 80])
            field = field_m.group(1).strip() if field_m else None
            if field:
                field = re.split(r"\s+(?:Minor|GPA|Expected|Graduated)\b", field)[0].strip()
            return level, field
    return None, None


def extract_school(text: str) -> str | None:
    m = SCHOOL_RE.search(text)
    if not m:
        return None
    return _SCHOOL_TRAILING.sub("", m.group(1)).strip()


def _all_dates(text: str) -> list[str]:
    dates = [month_year_to_iso(m.group(1), m.group(2)) for m in MONTH_YEAR_RE.finditer(text)]
    dates += [f"{int(y):04d}-{int(mo):02d}" for mo, y in NUMERIC_DATE_RE.findall(text)]
    return dates


def extract_grad_date(edu_text: str) -> str | None:
    dates = _all_dates(edu_text)
    return max(dates) if dates else None


def extract_gpa(text: str) -> float | None:
    m = GPA_RE.search(text)
    return float(m.group(1)) if m else None


def extract_skill_items(skills_text: str) -> list[str]:
    joined = re.sub(r"\s*\n\s*", " ", skills_text)
    # drop "Languages:"-style group labels
    joined = re.sub(r"\b[A-Z][A-Za-z ]{2,20}:\s*", ", ", joined)
    items = [i.strip(" .•-") for i in re.split(r"[,;•|]", joined)]
    return [i for i in items if i]


def extract_experience(exp_text: str) -> list[ExperienceEntry]:
    entries = []
    for line in exp_text.splitlines():
        m = DATE_RANGE_RE.search(line)
        if not m:
            continue
        head = line[: m.start()].strip(" |,–-")
        parts = [p.strip() for p in head.split("|") if p.strip()]
        if len(parts) >= 2:
            title, company = parts[0], parts[1]
        elif " at " in head:
            title, company = head.split(" at ", 1)
        else:
            title, company = head or None, None
        entries.append(ExperienceEntry(title=title, company=company, dates=m.group(0)))
    return entries


def parse_text(text: str, source: str = "<text>") -> ParsedResume:
    sections = split_sections(text)
    edu = sections.get("education", "")
    level, field = extract_degree(edu)
    return ParsedResume(
        source=source,
        raw_text=text,
        sections=sections,
        name=extract_name(text),
        email=(m.group(0) if (m := EMAIL_RE.search(text)) else None),
        phone=(m.group(0) if (m := PHONE_RE.search(text)) else None),
        degree_level=level,
        field_of_study=field,
        school=extract_school(edu),
        grad_date=extract_grad_date(edu),
        gpa=extract_gpa(text),
        skills=extract_skill_items(sections.get("skills", "")),
        experience=extract_experience(sections.get("experience", "")),
    )


def parse_resume(path: str | Path, drop_invisible: bool = False, layout_aware: bool = False) -> ParsedResume:
    """Parse a resume file. `layout_aware` changes only the reading order;
    section detection and field rules are identical in both modes."""
    text = extract_text(path, drop_invisible=drop_invisible, layout_aware=layout_aware)
    return parse_text(text, source=str(path))
