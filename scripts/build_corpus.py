"""Render every persona in every template, layout and format into data/resumes/.

    python scripts/build_corpus.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ats_sim.data import RESUME_DIR, load_personas, resume_path  # noqa: E402
from ats_sim.render import FORMATS, LAYOUTS, TEMPLATES, RenderOptions, render  # noqa: E402


def main(root: Path = RESUME_DIR) -> int:
    n = 0
    for p in load_personas():
        for template in TEMPLATES:
            for fmt in FORMATS:
                for layout in LAYOUTS:
                    render(p, layout, fmt, resume_path(p["id"], layout, fmt, root, template),
                           RenderOptions(template=template))
                    n += 1
    print(f"wrote {n} resumes to {root}")
    return n


if __name__ == "__main__":
    main()
