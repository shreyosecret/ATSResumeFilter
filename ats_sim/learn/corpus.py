"""Labeled training documents from the synthetic corpus."""
from __future__ import annotations

from pathlib import Path

from ..data import RESUME_DIR, load_personas, resume_path
from ..parser import extract_text
from ..render import FORMATS, LAYOUTS, TEMPLATES, RenderOptions, render
from .labels import label_lines, split_lines

Doc = tuple[list[str], list[str]]


def document(persona: dict, template: str, layout: str, fmt: str, root: Path = RESUME_DIR,
             cache: Path | None = None) -> Doc:
    """Layout-aware lines of one rendered resume and their labels. Renders into
    `cache` when the corpus was not built (a fresh install)."""
    path = resume_path(persona["id"], layout, fmt, root, template)
    if not path.exists():
        if cache is None:
            raise FileNotFoundError(path)
        path = resume_path(persona["id"], layout, fmt, Path(cache), template)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            render(persona, layout, fmt, path, RenderOptions(template=template))
    lines = split_lines(extract_text(path, layout_aware=True))
    return lines, label_lines(lines, persona, template)


def documents(templates=TEMPLATES, layouts=LAYOUTS, fmts=FORMATS, personas: list[dict] | None = None,
              root: Path = RESUME_DIR, cache: Path | None = None) -> dict[tuple, Doc]:
    personas = personas if personas is not None else load_personas()
    return {(p["id"], t, lay, f): document(p, t, lay, f, root, cache)
            for t in templates for lay in layouts for f in fmts for p in personas}
