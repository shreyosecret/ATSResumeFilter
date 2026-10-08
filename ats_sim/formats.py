"""Fifty generated resume formats for training the learned line tagger.

The five hand-written templates in render.py are the test bed for the
experiments; these are training variety. Each format is drawn from a seeded
spec: which content style it builds on (one of the five templates' line
styles), heading wording and capitalization, section order, a summary or
not, extra sections that belong to no parsed field (publications,
leadership, awards, volunteering, certifications, languages, interests),
bullet and date style, how the contact line is written, and the font.

They come from one generator written by one person, so they share its blind
spots; that is why the learned tagger is still evaluated on the hand-written
held-out templates and on generated formats it never trained on.

Twelve more, d01 to d12, are "designer" formats: the visual habits of
drag-and-drop resume builders, implemented here from a description (no
template from any builder is copied): letter-spaced headings, colored headings
with a rule under them, a large name with a one-line tagline, skills with
rating dots, and a shaded sidebar. These are the features that most often
confuse text-only parsers.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

N_FORMATS = 50
GENERATED_FORMATS = tuple(f"f{i:02d}" for i in range(1, N_FORMATS + 1))
TRAIN_FORMATS = GENERATED_FORMATS[:40]
HELD_OUT_FORMATS = GENERATED_FORMATS[40:]
DESIGNER_FORMATS = tuple(f"d{i:02d}" for i in range(1, 13))
TRAIN_DESIGNER = DESIGNER_FORMATS[:8]
HELD_OUT_DESIGNER = DESIGNER_FORMATS[8:]

STYLES = ("classic", "modern", "latex", "career_center", "hybrid")
HEADING_POOLS = {
    "contact": ["Contact", "Contact Information", "Get in Touch", "Reach Me", "Details", "Personal Details"],
    "summary": ["Summary", "Profile", "About Me", "Professional Summary", "Objective", "Career Objective",
                "Overview", "Professional Overview", "Personal Statement"],
    "education": ["Education", "Academic Background", "Academics", "Education and Training", "Schooling",
                  "Degrees", "Academic History", "Educational Background", "Education & Honors"],
    "experience": ["Experience", "Work Experience", "Professional Experience", "Employment History",
                   "Where I Have Worked", "Internships", "Relevant Experience", "Work History", "Career History",
                   "Industry Experience", "Positions Held"],
    "projects": ["Projects", "Technical Projects", "Selected Projects", "Personal Projects", "Things I Have Built",
                 "Research Projects", "Engineering Projects", "Portfolio", "Project Experience"],
    "skills": ["Skills", "Technical Skills", "Toolbox", "Tools & Technologies", "Core Skills", "Competencies",
               "Technical Proficiencies", "Expertise", "Skill Set", "Software & Tools"],
    "publications": ["Publications", "Papers", "Publications and Presentations", "Research Output"],
    "leadership": ["Leadership", "Leadership & Activities", "Campus Involvement", "Activities"],
    "awards": ["Awards", "Honors", "Honors & Awards", "Achievements"],
    "volunteering": ["Volunteering", "Volunteer Experience", "Community Service"],
    "certifications": ["Certifications", "Licenses & Certifications", "Certificates"],
    "languages": ["Languages", "Spoken Languages"],
    "interests": ["Interests", "Hobbies", "Outside the Lab"],
}
EXTRAS = ("publications", "leadership", "awards", "volunteering", "certifications", "languages", "interests")
CASES = ("upper", "title", "upper_colon", "title_colon", "small_caps_like")
BULLETS = ("•", "-", "–", "▪", "*", ">", "")
DATE_STYLES = ("short", "numeric", "long")
CONTACT_STYLES = ("as_style", "labeled", "one_line_labeled")
PDF_FONTS = ("Helvetica", "Times-Roman", "Courier")
DOCX_FONTS = ("Calibri", "Times New Roman", "Arial", "Garamond", "Georgia")
SUMMARIES = (
    "{field} {stage} focused on {s1} and {s2}.",
    "Seeking an internship where I can apply {s1}, {s2} and {s3} to real problems.",
    "Detail-oriented {field} {stage}; comfortable with {s1} and {s2}, eager to learn more.",
    "I build things with {s1} and {s2} and like turning data into decisions.",
)


@dataclass
class FormatSpec:
    name: str
    style: str
    headings: dict[str, str]
    order: list[str]
    summary: str | None
    extras: list[str]
    bullet: str
    date_style: str
    contact: str
    pdf_font: str
    docx_font: str
    heading_size: float
    notes: dict = field(default_factory=dict)
    design: dict = field(default_factory=dict)  # designer features (d01 to d12 only)
    layouts: tuple = ()  # preferred layouts for the training corpus; () means any


def _case(s: str, case: str) -> str:
    if case == "upper":
        return s.upper()
    if case == "upper_colon":
        return s.upper() + ":"
    if case == "title_colon":
        return s + ":"
    if case == "small_caps_like":
        return " ".join(w.lower() if w.lower() in {"and", "of", "the", "&", "in"} else w.upper() for w in s.split())
    return s


def make_spec(name: str) -> FormatSpec:
    rng = random.Random(f"ats-sim-format-{name}")
    style = rng.choice(STYLES)
    case = rng.choice(CASES)
    summary = rng.choice(SUMMARIES) if rng.random() < 0.55 else None
    extras = rng.sample(EXTRAS, k=rng.choice((0, 1, 1, 2, 2, 3)))
    keys = ["contact", *(["summary"] if summary else []), "education", "experience", "projects", "skills", *extras]
    headings = {k: _case(rng.choice(HEADING_POOLS[k]), case) for k in keys}
    core = ["education", "experience", "projects", "skills"]
    rng.shuffle(core)
    if rng.random() < 0.5:  # most real resumes keep experience before projects
        i, j = core.index("experience"), core.index("projects")
        if i > j:
            core[i], core[j] = core[j], core[i]
    order = (["summary"] if summary else []) + core
    for x in extras:  # extras usually trail, sometimes sit in the middle
        order.insert(rng.randint(len(order) // 2, len(order)), x)
    return FormatSpec(
        name=name, style=style, headings=headings, order=order, summary=summary, extras=extras,
        bullet=rng.choice(BULLETS), date_style=rng.choice(DATE_STYLES), contact=rng.choice(CONTACT_STYLES),
        pdf_font=rng.choice(PDF_FONTS), docx_font=rng.choice(DOCX_FONTS),
        heading_size=rng.choice((10.5, 11, 12, 13)), notes={"case": case})


HEADING_COLORS = ("#1F4E79", "#2E7D6B", "#7A2E8E", "#B5472B", "#3A3A3A", "#0B6E99")


def make_design_spec(name: str) -> FormatSpec:
    spec = make_spec(name)
    rng = random.Random(f"ats-sim-design-{name}")
    spec.design = {
        "tracked": rng.random() < 0.6, "heading_color": rng.choice(HEADING_COLORS), "rule": rng.random() < 0.6,
        "tagline": rng.random() < 0.8, "ratings": rng.random() < 0.5, "shaded": rng.random() < 0.6,
        "name_size": rng.choice((22, 24, 26, 28)),
    }
    if spec.design["tracked"]:
        spec.notes["case"] = "upper"
        spec.headings = {k: v.rstrip(":").upper() for k, v in spec.headings.items()}
    spec.bullet = rng.choice(("•", "▪", "–", ""))
    spec.layouts = ("two_column", "two_column", "single")
    return spec


SPECS = {n: make_spec(n) for n in GENERATED_FORMATS}
SPECS.update({n: make_design_spec(n) for n in DESIGNER_FORMATS})


def design(name: str) -> dict:
    s = SPECS.get(name)
    return s.design if s is not None else {}


def tagline(p: dict, name: str) -> str | None:
    """The one-line title under the name in designer formats."""
    if not design(name).get("tagline"):
        return None
    from .render import REFERENCE_DATE

    e = p["education"]
    return f"{e['field']} {'Student' if e['grad_date'] > REFERENCE_DATE else 'Graduate'}"


def heading(key: str, name: str) -> str:
    return SPECS[name].headings.get(key, key.title())


def _extra_lines(key: str, p: dict, rng: random.Random) -> list[tuple[str, str]]:
    e = p["education"]
    last = p["name"].split()[-1]
    first_initial = p["name"][0]
    year = int(e["grad_date"][:4])
    s = p["skills"] + ["data analysis"] * 3
    if key == "publications":
        return [("bullet", f"{last}, {first_initial}. and Rivera, J. ({year - 1}). Applying {s[0]} to "
                           f"{e['field'].lower()} problems: a case study. Undergraduate Research Symposium."),
                ("bullet", f"{last}, {first_initial}. ({year - 2}). Poster: lessons from a {s[1]} prototype. "
                           f"Regional Student Conference.")]
    if key == "leadership":
        role = rng.choice(("President", "Treasurer", "Outreach Chair", "Team Captain"))
        return [("bold", f"{role}, {e['field']} Student Society"),
                ("bullet", f"Organized {rng.randint(4, 12)} workshops for about {rng.randint(30, 120)} members")]
    if key == "awards":
        return [("text", f"Dean's List, {year - 3} to {year - 1}"),
                ("text", rng.choice(("Hackathon finalist", "Design competition, 2nd place",
                                     "Merit scholarship recipient")))]
    if key == "volunteering":
        return [("bold", rng.choice(("Volunteer Tutor, Riverside Public Library",
                                     "Habitat for Humanity, Build Volunteer", "Food Bank Shift Lead"))),
                ("bullet", "Helped about 20 people a week and trained new volunteers")]
    if key == "certifications":
        return [("text", ", ".join(rng.sample(["CPR and First Aid", "Lean Six Sigma Yellow Belt",
                                               "OSHA 10-Hour", "Google Data Analytics Certificate",
                                               "AWS Cloud Practitioner"], k=2)))]
    if key == "languages":
        return [("text", f"English (native), {rng.choice(('Spanish', 'Hindi', 'Mandarin', 'French'))} "
                         f"({rng.choice(('fluent', 'conversational', 'basic'))})")]
    if key == "interests":
        return [("text", ", ".join(rng.sample(["rock climbing", "chess", "film photography", "baking",
                                               "trail running", "jazz piano"], k=3)))]
    raise KeyError(key)


def _summary(spec: FormatSpec, p: dict) -> str:
    from .render import REFERENCE_DATE

    e = p["education"]
    s = (p["skills"] + ["teamwork"] * 3)[:3]
    return spec.summary.format(field=e["field"], stage="student" if e["grad_date"] > REFERENCE_DATE else "graduate",
                               s1=s[0], s2=s[1], s3=s[2])


def build(p: dict, opts) -> dict[str, list[tuple[str, str]]]:
    """Section lines for a generated format, in its order (same contract as render.blocks)."""
    import copy

    from . import render as R

    spec = SPECS[opts.template]
    base_opts = copy.copy(opts)
    base_opts.template = spec.style
    base_opts.date_style = spec.date_style
    base = getattr(R, R._BUILDERS[spec.style])(p, base_opts)
    rng = random.Random(f"{spec.name}-{p['id']}")

    if spec.contact == "labeled":
        contact = [("text", f"Email: {p['email']}"), ("text", f"Phone: {p['phone']}"), ("text", p["location"])]
    elif spec.contact == "one_line_labeled":
        contact = [("text", f"Email: {p['email']} | Phone: {p['phone']} | {p['location']}")]
    else:
        contact = base["contact"]
    out: dict[str, list[tuple[str, str]]] = {"contact": contact}
    for key in spec.order:
        if key == "summary":
            lines = [("text", _summary(spec, p))]
        elif key in EXTRAS:
            lines = _extra_lines(key, p, rng)
        else:
            lines = base.get(key, [])
        if key == "skills" and spec.design.get("ratings"):
            lines = [("rating", f"{sk}\t{rng.randint(3, 5)}") for sk in p["skills"]]
        if spec.bullet != "•":
            lines = [("text", f"{spec.bullet} {t}".strip()) if k == "bullet" else (k, t) for k, t in lines]
        out[key] = lines
    return out


def pdf_style(name: str) -> dict:
    s = SPECS.get(name)
    if s is None:
        return {}
    out = {"font": s.pdf_font, "heading_size": s.heading_size}
    if s.design:
        out.update(heading_color=s.design["heading_color"], name_size=s.design["name_size"])
    return out


def docx_font(name: str) -> str | None:
    s = SPECS.get(name)
    return None if s is None else s.docx_font


def describe() -> list[dict]:
    """One row per format, for the README table and the docs."""
    return [{"format": s.name, "style": s.style, "headings": " / ".join(s.headings[k] for k in s.order),
             "case": s.notes["case"], "bullet": s.bullet or "none", "dates": s.date_style, "contact": s.contact,
             "extras": ", ".join(s.extras) or "none", "pdf_font": s.pdf_font, "docx_font": s.docx_font,
             "design": ", ".join(k for k, v in s.design.items() if v is True) or "none",
             "split": "train" if s.name in TRAIN_FORMATS + TRAIN_DESIGNER else "held out"} for s in SPECS.values()]
