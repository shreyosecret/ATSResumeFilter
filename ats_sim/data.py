"""Loading the synthetic personas and (optionally) public Kaggle data."""
from __future__ import annotations

import json
import os
from pathlib import Path

import shutil
import sys


def user_dir() -> Path:
    """A writable per-user folder (the learned model also lives under it)."""
    base = os.environ.get("APPDATA") if os.name == "nt" else os.environ.get("XDG_DATA_HOME")
    return Path(base) / "ats_sim" if base else Path.home() / ".ats_sim"


def _frozen_root() -> Path:
    """In the packaged desktop app the bundled data is read-only and unpacked to
    a temporary folder on every launch, so copy it once (per app version) to a
    user folder, where the app can also write its generated resumes and caches."""
    from . import __version__

    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    home = user_dir() / "home"
    marker = home / ".version"
    if not marker.exists() or marker.read_text(encoding="utf-8") != __version__:
        for name in ("data", "results"):
            if (bundle / name).exists():
                shutil.copytree(bundle / name, home / name, dirs_exist_ok=True)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(__version__, encoding="utf-8")
    return home


if os.environ.get("ATS_SIM_HOME"):
    ROOT = Path(os.environ["ATS_SIM_HOME"]).resolve()
elif getattr(sys, "frozen", False):
    ROOT = _frozen_root()
else:
    ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESUME_DIR = DATA_DIR / "resumes"


def load_personas(path: str | Path | None = None) -> list[dict]:
    path = Path(path) if path else DATA_DIR / "personas.json"
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Data files not found at {DATA_DIR}. Install from a checkout of the repository "
            "(pip install -e .) or set ATS_SIM_HOME to the repository folder.")
    return json.loads(Path(path).read_text(encoding="utf-8"))["personas"]


def resume_path(persona_id: str, layout: str, fmt: str, root: Path = RESUME_DIR, template: str = "classic") -> Path:
    return root / template / fmt / layout / f"{persona_id}.{fmt}"


def load_kaggle_resumes(csv_path: str | Path, text_column: str = "Resume_str", limit: int | None = None,
                        category: str | list[str] | None = None, category_column: str = "Category",
                        seed: int = 0) -> list[tuple[str, str]]:
    """Load plain-text resumes from a Kaggle-format CSV as (id, text) pairs.

    Defaults match the public "Resume Dataset" (snehaanbhawal/resume-dataset,
    CC0; Resume.csv with columns ID, Resume_str, Resume_html, Category).
    `scripts/fetch_public_resumes.py` downloads it without a Kaggle account.
    These resumes have no layout and no answer key, so they are only used as
    extra candidates in ranking pools and as background documents for the
    scorers, never for the layout experiment. With `category`, `limit` is a
    per-category sample size (seeded, so runs are reproducible).
    """
    import pandas as pd

    df = pd.read_csv(csv_path)
    if category:
        cats = [category] if isinstance(category, str) else list(category)
        cats = [c.strip().upper() for c in cats]
        df = df[df[category_column].str.upper().isin(cats)]
        if limit:
            df = (df.groupby(category_column, group_keys=False)
                  .apply(lambda g: g.sample(min(limit, len(g)), random_state=seed)))
    elif limit:
        df = df.sample(min(limit, len(df)), random_state=seed)
    id_col = "ID" if "ID" in df.columns else None
    return [
        (f"public-{row[id_col] if id_col else i}", " ".join(str(row[text_column]).split()))
        for i, row in df.iterrows()
    ]
