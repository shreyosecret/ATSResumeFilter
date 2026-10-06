"""Render synthetic personas into resume files with controlled layouts.

Every layout carries the same content; only the visual arrangement changes.
That is what lets the layout experiment attribute extraction errors to the
layout alone.

Layouts:
  single     one column, headings above content (the "ATS-safe" template)
  two_column name on top, sidebar (contact, education, skills) beside the main
             column (experience, projects)
  table      the whole resume in a two-column table: section label | content
  textbox    single body column with contact details and skills placed in
             floating text boxes
"""
from __future__ import annotations

import copy
import html
from dataclasses import dataclass, field
from pathlib import Path

LAYOUTS = ("single", "two_column", "table", "textbox")
FORMATS = ("pdf", "docx")
REFERENCE_DATE = "2026-10"  # "today" for the synthetic data set; later grad dates are "Expected"

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class RenderOptions:
    date_style: str = "short"  # "short" -> Jun 2025, "numeric" -> 06/2025
    extra_sections: list[tuple[str, str]] = field(default_factory=list)  # visible (heading, body)
    hidden_text: str | None = None  # white text, invisible to a human reader


def fmt_date(iso: str, style: str = "short") -> str:
    if iso == "present":
        return "Present"
    y, m = iso.split("-")
    if style == "numeric":
        return f"{int(m):02d}/{y}"
    return f"{_MONTH_ABBR[int(m) - 1]} {y}"


# --------------------------------------------------------------- content model

def blocks(p: dict, opts: RenderOptions) -> dict[str, list[tuple[str, str]]]:
    """Lines per section as (kind, text); kind is 'text', 'bold' or 'bullet'."""
    e = p["education"]
    grad = fmt_date(e["grad_date"], opts.date_style)
    grad = f"Expected {grad}" if e["grad_date"] > REFERENCE_DATE else grad
    grad_line = grad + (f" | GPA: {e['gpa']:.2f}" if e.get("gpa") is not None else "")
    out: dict[str, list[tuple[str, str]]] = {
        "contact": [("text", p["email"]), ("text", p["phone"]), ("text", p["location"])],
        "education": [
            ("bold", f"{e['degree']} in {e['field']}"),
            ("text", f"{e['school']}, {e['location']}"),
            ("text", grad_line),
        ],
        "experience": [],
        "projects": [],
        "skills": [("text", ", ".join(p["skills"]))],
    }
    for x in p["experience"]:
        dates = f"{fmt_date(x['start'], opts.date_style)} – {fmt_date(x['end'], opts.date_style)}"
        out["experience"].append(("bold", f"{x['title']} | {x['company']} | {dates}"))
        out["experience"] += [("bullet", b) for b in x["bullets"]]
    for pr in p.get("projects", []):
        out["projects"].append(("bold", pr["name"]))
        out["projects"] += [("bullet", b) for b in pr["bullets"]]
    for heading, body in opts.extra_sections:
        out[heading.lower()] = [("text", body)]
    return out


HEADINGS = {
    "contact": "CONTACT", "education": "EDUCATION", "experience": "EXPERIENCE",
    "projects": "PROJECTS", "skills": "SKILLS",
}


def heading_for(key: str) -> str:
    return HEADINGS.get(key, key.upper())


def section_order(b: dict) -> list[str]:
    base = ["education", "experience", "projects", "skills"]
    return base + [k for k in b if k not in base and k != "contact"]


# ------------------------------------------------------------------- PDF

def _pdf_styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    ss = getSampleStyleSheet()
    return {
        "name": ParagraphStyle("name", parent=ss["Title"], fontSize=18, leading=22, alignment=0, spaceAfter=2),
        "contact": ParagraphStyle("contact", parent=ss["Normal"], fontSize=9.5, leading=12),
        "heading": ParagraphStyle("heading", parent=ss["Heading2"], fontSize=11, leading=14, spaceBefore=6, spaceAfter=2),
        "text": ParagraphStyle("text", parent=ss["Normal"], fontSize=9.5, leading=12),
        "bold": ParagraphStyle("bold", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, spaceBefore=3),
        "bullet": ParagraphStyle("bullet", parent=ss["Normal"], fontSize=9.5, leading=12, leftIndent=10, bulletIndent=2),
    }


def _flow(lines, st):
    from reportlab.platypus import Paragraph

    out = []
    for kind, text in lines:
        t = html.escape(text)
        if kind == "bullet":
            out.append(Paragraph(t, st["bullet"], bulletText="•"))
        else:
            out.append(Paragraph(t, st[kind]))
    return out


def _section_flow(key, b, st):
    from reportlab.platypus import Paragraph

    return [Paragraph(heading_for(key), st["heading"]), *_flow(b[key], st)]


def _hidden_painter(opts: RenderOptions):
    """Draw `opts.hidden_text` in white 8pt type along the bottom of page 1.

    White text at a normal size is the common form of this trick. (Very small
    text is also used, but pdfplumber merges sub-3pt lines into gibberish,
    which would confound the audit with a parser artifact.)
    """

    def paint(canvas, doc):
        if not opts.hidden_text or canvas.getPageNumber() != 1:
            return
        from reportlab.lib.colors import white
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph

        style = ParagraphStyle("hidden", fontName="Helvetica", fontSize=8, leading=10, textColor=white)
        para = Paragraph(html.escape(opts.hidden_text), style)
        width = letter[0] - 2 * 43
        _, h = para.wrap(width, letter[1])
        para.drawOn(canvas, 43, 30)
        _ = h

    return paint


def render_pdf(p: dict, layout: str, path: str | Path, opts: RenderOptions | None = None) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        BaseDocTemplate, Frame, FrameBreak, PageTemplate, Paragraph, SimpleDocTemplate, Table, TableStyle,
    )

    opts = opts or RenderOptions()
    st = _pdf_styles()
    b = blocks(p, opts)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = letter
    margin = 0.6 * inch
    hidden = _hidden_painter(opts)
    contact_line = " | ".join(t for _, t in b["contact"])

    if layout == "single":
        doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=margin, rightMargin=margin,
                                topMargin=margin, bottomMargin=margin)
        story = [Paragraph(html.escape(p["name"]), st["name"]), Paragraph(html.escape(contact_line), st["contact"])]
        for key in section_order(b):
            story += _section_flow(key, b, st)
        doc.build(story, onFirstPage=hidden, onLaterPages=hidden)

    elif layout == "two_column":
        doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=margin, rightMargin=margin,
                              topMargin=margin, bottomMargin=margin)
        header_h = 0.55 * inch
        body_top = H - margin - header_h
        side_w = 2.2 * inch
        gap = 0.25 * inch
        frames = [
            Frame(margin, body_top, W - 2 * margin, header_h, id="header", showBoundary=0),
            Frame(margin, margin, side_w, body_top - margin, id="side"),
            Frame(margin + side_w + gap, margin, W - 2 * margin - side_w - gap, body_top - margin, id="main"),
        ]
        doc.addPageTemplates([PageTemplate(id="two", frames=frames, onPage=hidden)])
        story = [Paragraph(html.escape(p["name"]), st["name"]), FrameBreak()]
        for key in ("contact", "education", "skills"):
            story += _section_flow(key, b, st)
        story.append(FrameBreak())
        for key in [k for k in section_order(b) if k not in ("education", "skills")]:
            story += _section_flow(key, b, st)
        doc.build(story)

    elif layout == "table":
        doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=margin, rightMargin=margin,
                                topMargin=margin, bottomMargin=margin)
        label_w = 1.3 * inch
        rows = [[Paragraph(html.escape(p["name"]), st["name"]), ""],
                [Paragraph("CONTACT", st["bold"]), Paragraph(html.escape(contact_line), st["text"])]]
        for key in section_order(b):
            rows.append([Paragraph(heading_for(key), st["bold"]), _flow(b[key], st)])
        t = Table(rows, colWidths=[label_w, W - 2 * margin - label_w])
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 1), (-1, -1), 0.4, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        doc.build([t], onFirstPage=hidden, onLaterPages=hidden)

    elif layout == "textbox":
        doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=margin, rightMargin=margin,
                              topMargin=margin, bottomMargin=margin)
        box_w = 2.3 * inch
        gap = 0.25 * inch
        main_w = W - 2 * margin - box_w - gap
        box_x = margin + main_w + gap

        def draw_box(canvas, x, top, title, lines):
            from reportlab.platypus import Frame as F

            items = [Paragraph(title, st["bold"]), *_flow(lines, st)]
            h = sum(i.wrap(box_w - 12, H)[1] + i.getSpaceBefore() for i in items) + 14
            canvas.setStrokeColor(colors.grey)
            canvas.setFillColor(colors.HexColor("#F2F4F7"))
            canvas.rect(x, top - h, box_w, h, stroke=1, fill=1)
            F(x, top - h, box_w, h, leftPadding=6, rightPadding=6, topPadding=4, bottomPadding=4).addFromList(items, canvas)

        def on_page(canvas, doc_):
            if canvas.getPageNumber() == 1:
                draw_box(canvas, box_x, H - margin, "CONTACT", b["contact"])
                draw_box(canvas, box_x, H - margin - 2.0 * inch, "SKILLS", b["skills"])
            hidden(canvas, doc_)

        frame = Frame(margin, margin, main_w, H - 2 * margin, id="main")
        doc.addPageTemplates([PageTemplate(id="tb", frames=[frame], onPage=on_page)])
        story = [Paragraph(html.escape(p["name"]), st["name"])]
        for key in [k for k in section_order(b) if k != "skills"]:
            story += _section_flow(key, b, st)
        doc.build(story)
    else:
        raise ValueError(f"unknown layout {layout!r}")
    return path


# ------------------------------------------------------------------- DOCX

_VML_SHAPETYPE = (
    '<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe">'
    '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>'
)


def _add_textbox(paragraph, lines: list[str], x_pt: float, y_pt: float, w_pt: float, h_pt: float, n: int) -> None:
    """Anchor a floating VML text box to `paragraph`. Its text lives in w:txbxContent."""
    from docx.oxml import parse_xml

    paras = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{html.escape(t)}</w:t></w:r></w:p>' for t in lines
    )
    xml = (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
        f'<w:pict>{_VML_SHAPETYPE if n == 1 else ""}'
        f'<v:shape id="TextBox{n}" o:spid="_x0000_s{1024 + n}" type="#_x0000_t202" '
        f'style="position:absolute;margin-left:{x_pt}pt;margin-top:{y_pt}pt;width:{w_pt}pt;height:{h_pt}pt;'
        f'z-index:{n};mso-position-horizontal-relative:margin;mso-position-vertical-relative:paragraph" '
        'fillcolor="#F2F4F7" strokecolor="#888888">'
        f'<v:textbox><w:txbxContent>{paras}</w:txbxContent></v:textbox></v:shape></w:pict></w:r>'
    )
    paragraph._p.append(parse_xml(xml))


def _docx_lines(container, lines):
    from docx.shared import Pt

    for kind, text in lines:
        if kind == "bullet":
            para = container.add_paragraph(f"• {text}")
            para.paragraph_format.left_indent = Pt(10)
        else:
            para = container.add_paragraph()
            run = para.add_run(text)
            run.bold = kind == "bold"
        para.paragraph_format.space_after = Pt(1)


def _docx_heading(container, key):
    from docx.shared import Pt

    para = container.add_paragraph()
    run = para.add_run(heading_for(key))
    run.bold = True
    run.font.size = Pt(12)
    para.paragraph_format.space_before = Pt(6)


def _first_para(cell):
    return cell.paragraphs[0]


def render_docx(p: dict, layout: str, path: str | Path, opts: RenderOptions | None = None) -> Path:
    import docx
    from docx.shared import Inches, Pt, RGBColor

    opts = opts or RenderOptions()
    b = blocks(p, opts)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    d = docx.Document()
    for s in d.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Inches(0.6)
    d.styles["Normal"].font.size = Pt(10)
    contact_line = " | ".join(t for _, t in b["contact"])

    name_para = d.add_paragraph()
    name_run = name_para.add_run(p["name"])
    name_run.bold = True
    name_run.font.size = Pt(18)

    if layout == "single":
        d.add_paragraph(contact_line)
        for key in section_order(b):
            _docx_heading(d, key)
            _docx_lines(d, b[key])

    elif layout == "two_column":
        t = d.add_table(rows=1, cols=2)
        t.autofit = False
        left, right = t.rows[0].cells
        for col, w in zip(t.columns, (Inches(2.3), Inches(5.0))):
            col.width = w
        left.width, right.width = Inches(2.3), Inches(5.0)
        for cell, keys in ((left, ("contact", "education", "skills")),
                           (right, [k for k in section_order(b) if k not in ("education", "skills")])):
            cell._tc.remove(_first_para(cell)._p)
            for key in keys:
                _docx_heading(cell, key)
                _docx_lines(cell, b[key])

    elif layout == "table":
        t = d.add_table(rows=0, cols=2)
        t.style = "Table Grid"
        t.autofit = False
        for col, w in zip(t.columns, (Inches(1.4), Inches(5.9))):
            col.width = w
        rows = [("contact", [("text", contact_line)])] + [(k, b[k]) for k in section_order(b)]
        for key, lines in rows:
            label, content = t.add_row().cells
            label.width, content.width = Inches(1.4), Inches(5.9)
            _first_para(label).add_run(heading_for(key)).bold = True
            content._tc.remove(_first_para(content)._p)
            _docx_lines(content, lines)

    elif layout == "textbox":
        _add_textbox(name_para, ["CONTACT", *[t for _, t in b["contact"]]], 330, 0, 190, 90, 1)
        d.add_paragraph()
        for key in [k for k in section_order(b) if k != "skills"]:
            if key == "experience":
                anchor = d.add_paragraph()
                _add_textbox(anchor, ["SKILLS", b["skills"][0][1]], 0, 0, 520, 60, 2)
                for _ in range(3):
                    d.add_paragraph()
            _docx_heading(d, key)
            _docx_lines(d, b[key])
    else:
        raise ValueError(f"unknown layout {layout!r}")

    if opts.hidden_text:
        run = d.add_paragraph().add_run(opts.hidden_text)
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    d.save(str(path))
    return path


def render(p: dict, layout: str, fmt: str, path: str | Path, opts: RenderOptions | None = None) -> Path:
    if fmt == "pdf":
        return render_pdf(p, layout, path, opts)
    if fmt == "docx":
        return render_docx(p, layout, path, opts)
    raise ValueError(f"unknown format {fmt!r}")


def plain_text(p: dict, opts: RenderOptions | None = None) -> str:
    """Single-column text with no file round trip (used for fast scorer-only checks)."""
    opts = opts or RenderOptions()
    b = blocks(p, opts)
    lines = [p["name"], " | ".join(t for _, t in b["contact"])]
    for key in section_order(b):
        lines.append(heading_for(key))
        lines += [("• " + t) if k == "bullet" else t for k, t in b[key]]
    if opts.hidden_text:
        lines.append(opts.hidden_text)
    return "\n".join(lines)


def clone(p: dict) -> dict:
    return copy.deepcopy(p)
