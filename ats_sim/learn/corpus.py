"""Labeled training documents from the synthetic corpus."""
from __future__ import annotations

from pathlib import Path

from ..data import RESUME_DIR, load_personas, resume_path
from ..render import FORMATS, LAYOUTS, TEMPLATES, RenderOptions, render
from .geometry import read
from .labels import label_lines

Doc = tuple[list[str], list[str], list[list[float]]]  # lines, labels, page geometry


def document(persona: dict, template: str, layout: str, fmt: str, root: Path = RESUME_DIR,
             cache: Path | None = None) -> Doc:
    """Layout-aware lines of one rendered resume, their labels and their page
    geometry. Renders into `cache` when the corpus was not built (a fresh install)."""
    path = resume_path(persona["id"], layout, fmt, root, template)
    if not path.exists():
        if cache is None:
            raise FileNotFoundError(path)
        path = resume_path(persona["id"], layout, fmt, Path(cache), template)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            render(persona, layout, fmt, path, RenderOptions(template=template))
    rows = read(path)
    lines = [r.text for r in rows]
    return lines, label_lines(lines, persona, template), [r.geo for r in rows]


def documents(templates=TEMPLATES, layouts=LAYOUTS, fmts=FORMATS, personas: list[dict] | None = None,
              root: Path = RESUME_DIR, cache: Path | None = None) -> dict[tuple, Doc]:
    personas = personas if personas is not None else load_personas()
    return {(p["id"], t, lay, f): document(p, t, lay, f, root, cache)
            for t in templates for lay in layouts for f in fmts for p in personas}


def format_combos(formats, personas: list[dict], per_persona: int = 1, seed: int = 0) -> list[tuple]:
    """(persona id, format, layout, file type) keys: each persona appears in every
    format in `per_persona` layout and file-type combinations drawn at random
    (seeded), so 50 formats cost 50 x 16 files instead of 50 x 128."""
    import random

    from ..formats import SPECS

    keys = []
    for fmt_name in formats:
        layouts = SPECS[fmt_name].layouts or LAYOUTS  # designer formats favor two columns
        combos = [(lay, f) for lay in layouts for f in FORMATS]
        rng = random.Random(f"{seed}-{fmt_name}")
        for p in personas:
            for lay, f in rng.sample(combos, per_persona):
                keys.append((p["id"], fmt_name, lay, f))
    return keys


def format_documents(formats, personas: list[dict] | None = None, per_persona: int = 1, seed: int = 0,
                     root: Path = RESUME_DIR, cache: Path | None = None) -> dict[tuple, Doc]:
    personas = personas if personas is not None else load_personas()
    by_id = {p["id"]: p for p in personas}
    return {k: document(by_id[k[0]], k[1], k[2], k[3], root, cache)
            for k in format_combos(formats, personas, per_persona, seed)}
